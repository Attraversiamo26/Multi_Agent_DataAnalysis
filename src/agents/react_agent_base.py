import json
import logging
import traceback
import uuid
from abc import abstractmethod, ABC
from typing import List, Dict, Any, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph.message import push_message

from src.entity.planner_model import Step
from src.entity.states import StepState
from src.llms.llm import get_llm_by_name
from src.prompts.template import apply_prompt_template
from src.utils.output_utils import repair_json_output
from src.utils.llm_utils import astream
from src.utils.rag_helper import RAGHelper
from src.utils.tag_manager import tag_scope, MessageTag
from src.utils.tools import terminate, feedback

logger = logging.getLogger(__name__)

# Constants
THINK_PROMPT_NO_EXPLAIN = """
基于当前状态，决定下一步做什么。注意：仅执行当前任务：{task_description}

在决定下一步行动之前，请仔细阅读当前任务、上一步的结果、原始用户问题和先前执行的步骤。

请严格参考以下检索到的信息。指标计算公式必须严格遵循检索到的信息。特别注意默认规则——当用户没有明确指定某些内容时，使用检索到的信息中的默认规则。

## 检索到的信息如下：
{retrieve_info}

# 注意：
**如果工具调用多次失败，请调用`terminate`工具结束任务，并简要说明调用失败原因**
""".strip()

THINK_PROMPT_WITH_EXPLAIN = """
基于当前状态，思考下一步做什么。注意：仅执行当前任务：{task_description}

# 核心规则
仔细阅读当前任务和上一次操作的结果，然后：
1. 在响应中简要介绍要调用的具体工具名称和参数
2. 推理和函数调用必须在同一个响应中返回——两者都不能缺少。
3. 性能考虑
- **批量检索与迭代检索**：批量检索 + pandas处理比多次API调用更快
- **过滤阈值**：当通过大列表（>=10项）过滤时，一次性检索完整数据集并在本地过滤，而不是进行过多的参数化调用。这种方法不仅更快，而且还降低了因传递大量参数而导致错误的风险。
- **聚合位置**：在支持时在数据源执行聚合（例如，GraphQL groupBy、数据库SUM/AVG）以减少数据传输
4. 不执行任何与任务无关的分析或计算
5. 调用`run_python_code`工具时，不要生成像"报告"这样的词
6. 当某些数据或指标无法获取时，不要模拟、猜测或替代——只需在任务结束时诚实地报告情况

# 严格遵循
请严格参考以下检索到的信息。任务所需指标的计算公式、字段和默认值必须严格遵循检索到的信息。特别注意默认规则——当用户没有明确指定某些内容时，使用检索到的信息中的默认规则。

## 检索到的信息如下：
{retrieve_info}


# 错误示例（禁止）

❌ 错误1：仅返回推理而不返回函数调用
❌ 错误2：仅返回函数调用而不返回推理
❌ 错误3：在推理中提及具体的工具名称

# 注意：
**工具调用必须以函数调用格式返回，而不是像"调用工具：..."这样的文本输出**
**如果工具调用多次失败，请调用`terminate`工具结束任务**
""".strip()

SAME_ANSWER_PROMPT = "检测到与之前相同的答案。请避免重复相同的响应，改为生成新答案"


class ReActAgentBase(ABC):

    def __init__(
        self,
        agent_name: str,
        *,
        mcp_servers: dict | None = None,
        max_iterations: int = 10,
        react_llm: str = "react_agent",
    ):
        self.agent_name = agent_name
        self.mcp_servers = mcp_servers or {}
        self.max_iterations = max_iterations
        self.react_llm = react_llm
        self.tools = None
        self.workspace_directory = None
        self.current_step: Step = None
        self.retrieve_info = 'None available'

    @staticmethod
    def _generate_record_id() -> str:
        """Generate a unique record ID for message tracking."""
        return f"record-{str(uuid.uuid4())}"

    @staticmethod
    def _normalize_tool_calls(calls: List[Dict]) -> tuple:
        """Normalize tool calls for signature comparison."""
        normalized = []
        for tc in calls or []:
            name = tc.get('name', '')
            args = tc.get('args', tc.get('arguments', {}))
            if isinstance(args, dict):
                args = sorted(args.items())
            normalized.append((name, str(args)))
        return tuple(normalized)

    def _make_think_signature(self, think_res) -> str:
        """Create a unique signature for think results to detect duplicates."""
        try:
            signature_obj = {
                "content": getattr(think_res, 'content', ''),
                "tool_calls": self._normalize_tool_calls(getattr(think_res, 'tool_calls', []) or []),
                "invalid_tool_calls": self._normalize_tool_calls(getattr(think_res, 'invalid_tool_calls', []) or []),
            }
            return json.dumps(signature_obj, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(think_res)

    async def retrieve_step_information(self, step_title: str, step_description: str, config) -> str:
        """
        Perform RAG retrieval based on the current step's title and description.

        Args:
            step_title: Title of the current step
            step_description: Description of the current step
            config: Runnable configuration

        Returns:
            Retrieved relevant information formatted as a string
        """
        try:
            # Initialize RAG helper
            extract_llm = get_llm_by_name("extract")
            rag_helper = RAGHelper(extract_llm)

            # Build search query - using title and description
            query = f"{step_title}\n{step_description}"

            # Perform retrieval with optional dataset filtering
            retrieved_info = await rag_helper.retrieve_information(
                question=query,
                config=config,
                dataset=self.agent_name,  # Use agent name as dataset filter
                include_agent_data_sources=False
            )

            if retrieved_info:
                return retrieved_info
            else:
                return ""

        except Exception as e:
            logger.warning(f"RAG retrieval failed for step '{step_title}': {str(e)}. Continuing without retrieval.")
            return ""

    async def _think(self, no_action: bool, llm, tools, think_messages: List[Dict], 
                     retrieve_info: str, config: RunnableConfig) -> Tuple[bool, Any]:
        """Execute the thinking step of the agent."""
        # Skip adding prompt if checking for same answer
        if 'same answer' not in think_messages[-1]['content']:
            prompt = THINK_PROMPT_NO_EXPLAIN if no_action else THINK_PROMPT_WITH_EXPLAIN
            # 安全获取task_description
            task_description = self.current_step.description if self.current_step else "Data retrieval task"
            content = prompt.format(
                task_description=task_description,
                retrieve_info=retrieve_info
            )
            think_messages.append({"role": "user", "content": content})
        
        logger.info(f"Think messages: {think_messages}.")
        
        model_with_tools = llm.bind_tools(tools, tool_choice="auto")
        result = await astream(
            model_with_tools, 
            think_messages,
            {"thinking": {"type": "enabled"}, "temperature": 0.01}, 
            config
        )
        
        # Check if there are valid tool calls
        has_tool_calls = len(result.tool_calls) > 0 or len(result.invalid_tool_calls) > 0
        
        return has_tool_calls, result

    def _parse_tool_args(self, tool_call: Dict) -> Dict:
        """Parse and normalize tool arguments."""
        args = tool_call.get('args') or tool_call.get('arguments')
        if isinstance(args, str):
            args = json.loads(repair_json_output(args))
        return args

    def _parse_result(self, result: Any) -> Any:
        """Parse string results to JSON if possible."""
        if not isinstance(result, str):
            return result
        try:
            return json.loads(repair_json_output(result))
        except Exception:
            return result

    async def _execute_single_tool(self, tool_call: Dict, tool_map: Dict, 
                                   messages: List[Dict], results: List[Dict]) -> Dict | None:
        """Execute a single tool call. Returns termination dict if tool is terminate/feedback, None otherwise."""
        tool_name = str(tool_call['name']).strip()
        if not tool_name:
            return {"terminate": "unknown"}
        
        tool = tool_map.get(tool_name)
        args = self._parse_tool_args(tool_call)
        
        # Execute tool
        if args is None:
            args = {}
        result = await tool.ainvoke(args)
        exec_msg = {"role": "tool", "tool_call_id": tool_call['id'], "content": result}
        messages.append(exec_msg)
        
        # Handle special tools
        if tool_name == 'terminate':
            parsed_result = self._parse_result(result)
            results.append({"tool_called": tool_name, "arguments": args, "result": parsed_result})
            return {"terminate": result}
        
        if tool_name == 'feedback':
            return {"terminate": "failure"}
        
        # Handle normal tools
        if 'Exception' not in result and 'Error' not in result:
            parsed_result = self._parse_result(result)
            results.append({"tool_called": tool_name, "arguments": args, "result": parsed_result})
        
        logger.info(exec_msg)
        return None

    async def _action(self, think_res, tool_map: Dict, messages: List[Dict], 
                     results: List[Dict]) -> Dict | List[Dict]:
        """Execute actions based on tool calls from the thinking step."""
        tool_calls = think_res.invalid_tool_calls or think_res.tool_calls
        messages.append({
            "role": "assistant", 
            "content": think_res.content, 
            "tool_calls": tool_calls
        })
        
        for tool_call in tool_calls:
            try:
                termination = await self._execute_single_tool(tool_call, tool_map, messages, results)
                if termination:
                    return termination
            except Exception:
                err_msg = {
                    "role": "tool", 
                    "tool_call_id": tool_call['id'], 
                    "content": f"Error: {traceback.format_exc()}"
                }
                messages.append(err_msg)
        
        return results

    async def build_tools(self):
        tools = []
        if self.mcp_servers:
            try:
                mcp_client = MultiServerMCPClient(self.mcp_servers)
                tools.extend(await mcp_client.get_tools())
            except Exception as e:
                logger.warning(f"Failed to connect to MCP servers: {e}, continuing without MCP tools")
        tools.append(terminate)
        tools.append(feedback)
        return tools

    def _check_duplicate_response(self, think_signatures: List[str], 
                                   step_messages: List[Dict], 
                                   first_same_question: bool) -> Tuple[bool, bool]:
        """Check if the agent is generating duplicate responses."""
        if len(think_signatures) < 2 or think_signatures[-1] != think_signatures[-2]:
            return first_same_question, False
        
        logger.info("The same answer as before has been detected.")
        if first_same_question:
            step_messages.append({"role": "user", "content": SAME_ANSWER_PROMPT})
            return False, False
        return first_same_question, True

    async def _execute_agent_step(self, step_state: StepState, config: RunnableConfig):
        """Main execution loop for the agent."""
        if self.retrieve_info == 'None available' and self.current_step:
            try:
                # 获取step_title和step_description
                step_title = self.current_step.title if hasattr(self.current_step, 'title') else "Unknown Step"
                step_description = self.current_step.description if hasattr(self.current_step, 'description') else "No description available"
                
                retrieved_info = await self.retrieve_step_information(
                    step_title=step_title,
                    step_description=step_description,
                    config=config
                )
                if retrieved_info:
                    self.retrieve_info = retrieved_info
                    logger.info(f"RAG retrieval successful for step: {step_title}")
                else:
                    logger.warning(f"No RAG information retrieved for step: {step_title}")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {str(e)}. Using default retrieve_info.")
        
        llm = get_llm_by_name(self.react_llm)
        tool_map = {t.name: t for t in self.tools}

        input_ = {
            "messages": step_state.get('history', []),
            "locale": step_state.get("locale"),
            "workspace_directory": self.workspace_directory
        }
        step_messages = apply_prompt_template("react_agent", input_)
        results: List[Dict] = []
        think_signatures: List[str] = []
        first_no_action = True
        no_action = False
        first_same_question = True
        
        for i in range(self.max_iterations):
            # Check for duplicate responses after first iteration
            if i > 0:
                first_same_question, should_terminate = self._check_duplicate_response(
                    think_signatures, step_messages, first_same_question
                )
                if should_terminate:
                    return {"terminate": "unknown"}, results
            
            # Think step
            with tag_scope(config, MessageTag.THINK):
                has_action, think_res = await self._think(
                    no_action, llm, self.tools, step_messages, self.retrieve_info, config
                )
            
            # Track thinking signatures for duplicate detection
            try:
                think_signatures.append(self._make_think_signature(think_res))
            except Exception:
                pass
            
            # Action step
            if has_action:
                first_no_action = True
                action_res = await self._action(
                    think_res=think_res, 
                    tool_map=tool_map, 
                    messages=step_messages, 
                    results=results
                )
                if isinstance(action_res, dict) and action_res.get("terminate") is not None:
                    return action_res, results
            else:
                # Handle no action case
                no_action = True
                if first_no_action:
                    push_message(HumanMessage(
                        content=f"Analysis result: {think_res.content}", 
                        id=self._generate_record_id()
                    ))
                    step_messages.pop()
                    first_no_action = False
                else:
                    break

        return {"terminate": "unknown"}, results

    @abstractmethod
    def run(self, state: StepState, config: RunnableConfig):
        """
        Execute the sub-agent's task.

        Args:
            state (StepState): The current execution state containing workspace
                              directory, current step, and other context information
            config (RunnableConfig): Configuration settings for the runnable execution
        """
        pass