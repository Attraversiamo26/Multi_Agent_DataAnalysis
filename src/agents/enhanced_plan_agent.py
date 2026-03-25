import json
import logging
import traceback
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message
from langgraph.types import Command

from src.agents.analysis_agent import AnalysisAgent
from src.agents.search_agent import SearchAgent
from src.agents.visualization_agent import VisualizationAgent
from src.agents.generate_agent import GenerateAgent
from src.agents.manage_agent import ManageAgent
from src.agents.knowledge_agent import KnowledgeAgent
from src.config.loader import load_yaml_config
from src.entity.states import PlanState
from src.entity.planner_model import Plan
from src.entity.enhanced_states import StepExecutionRecord, ExecutionStatus, GeneratedCodeFile
from src.llms.llm import get_llm_by_name
from src.prompts.template import apply_prompt_template
from src.utils.agent_utils import create_task_description_handoff_tool
from src.utils.output_utils import repair_json_output
from src.utils.llm_utils import astream
from src.utils.rag_helper import RAGHelper
from src.utils.tag_manager import tag_scope, MessageTag
from src.utils.report_intent_recognizer import ReportIntentRecognizer
from src.utils.code_manager import CodeManager

logger = logging.getLogger(__name__)


class EnhancedPlanAgent:
    """增强版PlanAgent，包含标准JSON输出、动态计划调整和代码管理"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.agent_tools = [
            create_task_description_handoff_tool(agent=SearchAgent(agent_name="search_agent")),
            create_task_description_handoff_tool(agent=AnalysisAgent(agent_name="analysis_agent")),
            create_task_description_handoff_tool(agent=VisualizationAgent(agent_name="visualization_agent")),
            create_task_description_handoff_tool(agent=GenerateAgent(agent_name="generate_agent")),
            create_task_description_handoff_tool(agent=ManageAgent(agent_name="manage_agent")),
            create_task_description_handoff_tool(agent=KnowledgeAgent(agent_name="knowledge_agent"))
        ]
        self.llm = get_llm_by_name(self.agent_name)
        self.extract_llm = get_llm_by_name("extract")
        
        self.report_intent_recognizer = ReportIntentRecognizer()
        self.config = None
        self.capabilities = None
        self.agent_capabilities = None
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        self.config = load_yaml_config("conf.yaml")
        capabilities = self.config.get("agents", {}).get("capabilities", {})
        self.agent_capabilities = json.dumps(capabilities, ensure_ascii=False, indent=2)
        agent_config = self.config.get("app", {})
        
        self.max_steps = agent_config.get("max_steps", 6)
        self.max_retry_count = agent_config.get("max_retry_count", 3)
        self.max_replan_count = agent_config.get("max_replan_count", 10)
        self.plan_temperature = agent_config.get("plan_temperature", 1.0)
        
        self.rag_helper = RAGHelper(self.extract_llm)
    
    def _create_step_execution_record(
        self,
        step_name: str,
        tool_used: str,
        status: ExecutionStatus,
        result: any = None,
        error_message: str = None
    ) -> StepExecutionRecord:
        """创建标准的步骤执行记录"""
        record = StepExecutionRecord(
            step_name=step_name,
            tool_used=tool_used,
            execution_status=status,
            result=result
        )
        record.mark_complete(status, result, error_message)
        
        logger.info(f"Step execution record: {json.dumps(record.to_json(), ensure_ascii=False, indent=2)}")
        return record
    
    def _should_adjust_plan(self, current_plan, executed_steps, state) -> tuple[bool, str]:
        """判断是否需要调整计划"""
        if not current_plan or not hasattr(current_plan, 'steps'):
            return False, "No valid plan"
        
        # 检查是否有失败的步骤
        for step in executed_steps:
            if step.final_status == "failure":
                return True, f"Step '{step.description}' failed"
        
        # 检查执行结果是否满足后续步骤需求
        # 这里可以添加更复杂的逻辑
        return False, "Plan looks good"
    
    def _adjust_plan_based_on_results(self, current_plan, executed_steps, state):
        """根据执行结果动态调整计划"""
        should_adjust, reason = self._should_adjust_plan(current_plan, executed_steps, state)
        
        if not should_adjust:
            return current_plan, False
        
        logger.info(f"Adjusting plan: {reason}")
        
        # 简单的调整策略：移除失败步骤后的所有步骤，或修改后续步骤
        # 实际生产中可以使用LLM来重新规划
        adjusted_plan = current_plan.model_copy()
        
        # 找到失败的步骤
        failed_step_index = None
        for i, step in enumerate(executed_steps):
            if step.final_status == "failure":
                failed_step_index = i
                break
        
        if failed_step_index is not None:
            # 只保留失败步骤前的已执行步骤
            # 实际中可以添加重试或替代步骤
            adjusted_plan.steps = adjusted_plan.steps[:failed_step_index + 1]
        
        return adjusted_plan, True
    
    async def _execute_single_step(
        self,
        step,
        step_index: int,
        state: PlanState,
        current_plan: Plan,
        config: RunnableConfig,
        code_manager: CodeManager
    ) -> tuple[StepExecutionRecord, any]:
        """执行单个步骤并返回标准JSON记录"""
        start_time = datetime.now()
        
        step_name = step.title if hasattr(step, 'title') else f"Step {step_index + 1}"
        tool_used = step.agent
        
        logger.info(f"Executing step {step_index + 1}: {step_name} using {tool_used}")
        
        try:
            # 执行步骤（复用原有逻辑）
            user_question = state['user_question']
            plan_overview = self._build_plan_overview(state, user_question, current_plan, step_index)
            step_context = self._create_step_instruction(state, user_question, current_plan, step, step_index)
            
            tool = self._get_tool_for_agent(step.agent)
            res_dict = await tool.ainvoke({
                "messages": step_context,
                "workspace_directory": state["workspace_directory"],
                "current_step": step,
                "locale": state.get("locale"),
                "config": config
            })
            
            res = res_dict['execute_res']
            
            # 处理结果
            action_res, results = self._process_agent_result(res)
            
            # 从结果内容中提取并保存Python代码
            content_to_extract = ""
            if hasattr(res, 'generated_code') and res.generated_code:
                content_to_extract = res.generated_code
            elif hasattr(res, 'content'):
                content_to_extract = res.content
            elif hasattr(res, 'data_summary'):
                content_to_extract = str(res.data_summary)
            elif isinstance(results, list) and len(results) > 0:
                content_to_extract = str(results)
            
            if content_to_extract:
                code_files = code_manager.create_code_files_from_content(
                    content_to_extract,
                    filename_prefix=f"{step.agent}_step{step_index + 1}"
                )
                if code_files:
                    logger.info(f"Saved {len(code_files)} code files from step {step_index + 1}")
                    # 将保存的代码文件信息添加到结果中
                    for code_file in code_files:
                        if not hasattr(res, 'generated_code_files'):
                            res.generated_code_files = []
                        res.generated_code_files.append(code_file.to_dict())
            
            # 构建标准执行记录
            execution_record = StepExecutionRecord(
                step_name=step_name,
                tool_used=tool_used,
                execution_status=ExecutionStatus.SUCCESS,
                result=results
            )
            execution_record.mark_complete(ExecutionStatus.SUCCESS, results)
            
            # 解析结果中的子步骤（从搜索Agent的输出中）
            self._parse_and_add_sub_steps(execution_record, results)
            
            # 输出标准JSON
            final_json_output = execution_record.to_json()
            logger.info(f"Step completed. Output: {json.dumps(final_json_output, ensure_ascii=False, indent=2)}")
            
            # 只输出标准JSON，不包含其他内容
            push_message(AIMessage(
                content=json.dumps(final_json_output, ensure_ascii=False, indent=2),
                id=f"step-output-{str(uuid.uuid4())}"
            ))
            
            return execution_record, res
            
        except Exception as e:
            logger.error(f"Error executing step {step_index + 1}: {str(e)}")
            logger.error(traceback.format_exc())
            
            error_record = StepExecutionRecord(
                step_name=step_name,
                tool_used=tool_used,
                execution_status=ExecutionStatus.FAILED,
                result=None
            )
            error_record.mark_complete(ExecutionStatus.FAILED, None, str(e))
            
            return error_record, None
    
    def _build_plan_overview(self, state, user_question, current_plan, current_step_index):
        """构建计划概览"""
        executed_results = []
        for executed_step in state.get('executed_steps', []):
            status_emoji = "✅" if executed_step.final_status == "success" else "❌"
            result = executed_step.summary_execution_res if executed_step.summary_execution_res else executed_step.execution_res
            executed_results.append(f"{status_emoji} Task: {executed_step.description}\nAgent: {executed_step.agent}\nResult: {result}")
        
        plan_steps = []
        for i, step in enumerate(current_plan.steps):
            if i < current_step_index:
                plan_steps.append(f"  ✅ Step {i + 1} ({step.agent}): {step.description}")
            elif i == current_step_index:
                plan_steps.append(f"  ➡️ Step {i + 1} ({step.agent}): {step.description} [current task]")
            else:
                plan_steps.append(f"  ⏳ Step {i + 1} ({step.agent}): {step.description}")
        
        if len(executed_results) == 0:
            executed_results = ["None"]
        
        return f"""
## Original User Question
{user_question} 

## Previously Executed Steps
{"\n".join(executed_results)}

## 📋 Current Plan
Reasoning: {current_plan.thought}
Title: {current_plan.title}
Execution Steps:
{chr(10).join(plan_steps)}
"""
    
    def _create_step_instruction(self, state, user_question, current_plan, current_step, step_index):
        """创建步骤执行指令"""
        plan_overview = self._build_plan_overview(state, user_question, current_plan, step_index)
        return [{"role": "user", "content": f"""
            {plan_overview}

            ## 🎯 Current Task Focus
            Step {step_index + 1}/{len(current_plan.steps)}: {current_step.description}

            ## 📌 Execution Requirements
            - Focus on completing the current step, refer to the overall plan to ensure output format meets the needs of subsequent steps
            - After execution is complete, call the terminate() tool to report status
            - Consider the requirements of subsequent steps, but do not deviate from the core objective of the current task
            """}]
    
    def _process_agent_result(self, res):
        """处理Agent返回的结果"""
        if hasattr(res, 'data_summary') and hasattr(res, 'success'):
            action_res = {"terminate": "success" if res.success else "failure"}
            results = [res.data_summary] if hasattr(res, 'data_summary') and res.data_summary else []
        else:
            try:
                action_res, results = res
            except (ValueError, TypeError):
                action_res = {"terminate": "success"}
                results = [res]
        return action_res, results
    
    def _get_tool_for_agent(self, agent_name: str):
        """获取对应Agent的工具"""
        tool_name = f"transfer_to_{agent_name}"
        matching_tools = [t for t in self.agent_tools if t.name == tool_name]
        if not matching_tools:
            raise ValueError(f"No tool found for agent: {agent_name}")
        return matching_tools[0]
    
    async def run(self, state: PlanState, config: RunnableConfig):
        """主运行方法"""
        logger.info(f"[EnhancedPlanAgent] Starting...")
        
        self._load_config()
        
        current_plan = state.get("current_plan")
        last_plan = current_plan
        executed_steps = state.get('executed_steps', [])
        messages = state.get("history", [])
        retrieved_info = state.get("retrieved_info", "")
        user_question = state.get('user_question', "")
        replan_cnt = state.get("replan_cnt", 0)
        need_replan = state.get("need_replan", True)
        
        # 初始化代码管理器
        workspace_dir = state.get("workspace_directory", "")
        code_manager = CodeManager(workspace_dir)
        
        # 处理已有计划的重新规划
        if current_plan is not None and need_replan:
            push_message(HumanMessage(
                content=f"Adjusting plan based on execution results",
                id=f"record-{str(uuid.uuid4())}"
            ))
            
            if replan_cnt > self.max_replan_count:
                return Command(update={}, goto="__end__")
            
            current_plan, adjusted = self._adjust_plan_based_on_results(
                current_plan, executed_steps, state
            )
            
            if adjusted:
                logger.info("Plan adjusted successfully")
        
        # 生成初始计划
        if current_plan is None:
            with tag_scope(config, MessageTag.THINK):
                push_message(HumanMessage(
                    content=f"Analyzing the problem...",
                    id=f"record-{str(uuid.uuid4())}"
                ))
                
                try:
                    retrieved_info = await self.rag_helper.retrieve_information(
                        user_question, config
                    )
                except Exception as e:
                    logger.warning(f"Information retrieval failed: {str(e)}")
                    retrieved_info = ""
            
            push_message(HumanMessage(
                content=f"Creating execution plan",
                id=f"record-{str(uuid.uuid4())}"
            ))
            
            current_plan = await self._generate_initial_plan(
                messages, user_question, retrieved_info, config
            )
            messages.append({"role": "assistant", "content": current_plan.model_dump_json()})
        
        # 检查是否需要询问用户
        questions = current_plan.questions if hasattr(current_plan, 'questions') else []
        if len(questions) > 0 and need_replan:
            ask_user_question = ". \n".join([q.question for q in questions])
            return Command(
                update={
                    "current_plan": current_plan,
                    "executed_steps": executed_steps,
                    "history": [msg for msg in messages if msg['role'] != 'system'],
                    "replan_cnt": replan_cnt + 1,
                    "retrieved_info": retrieved_info,
                    "ask_user_question": ask_user_question
                },
                goto="ask_user"
            )
        
        # 执行计划步骤
        if isinstance(current_plan, Plan) and len(current_plan.steps) > 0:
            current_step_index = len(executed_steps)
            
            if current_step_index < len(current_plan.steps):
                step = current_plan.steps[current_step_index]
                
                # 执行单个步骤
                execution_record, step_result = await self._execute_single_step(
                    step, current_step_index, state, current_plan, config, code_manager
                )
                
                # 更新步骤状态
                step.execution_res = execution_record.result
                step.summary_execution_res = execution_record.result
                step.final_status = execution_record.execution_status.value
                executed_steps.append(step)
                
                # 检查是否还有更多步骤
                if len(executed_steps) < len(current_plan.steps):
                    return Command(
                        update={
                            "current_plan": current_plan,
                            "executed_steps": executed_steps,
                            "replan_cnt": replan_cnt + 1,
                            "need_replan": False,
                            "retrieved_info": retrieved_info
                        },
                        goto="plan_agent"
                    )
                else:
                    return await self._decide_report_or_end(
                        state, last_plan, executed_steps, user_question
                    )
            else:
                return await self._decide_report_or_end(
                    state, last_plan, executed_steps, user_question
                )
        else:
            return await self._decide_report_or_end(
                state, last_plan, executed_steps, user_question
            )
    
    async def _generate_initial_plan(self, messages, user_question, retrieved_info, config):
        """生成初始计划"""
        if retrieved_info:
            user_prompt = f"""
            Create a plan to solve this question: {user_question}

            Please refer to the following retrieved information when developing your plan:
            **Retrieved context:**
            ---------------------Retrieved context START--------------------
            {retrieved_info}
            ---------------------Retrieved context END--------------------

            **Requirements:**
            - Use insights from the retrieved context
            - Reference specific information from the context in your plan
            """
        else:
            user_prompt = f"Create a plan to solve this question: {user_question}"
        
        messages.append({"role": "user", "content": user_prompt})
        
        input_ = {
            "messages": messages,
            "AGENT_CAPABILITIES": self.agent_capabilities,
            "locale": self.config.get("app", {}).get("locale", "zh-CN")
        }
        
        plan_messages = apply_prompt_template(self.agent_name, input_)
        return await self._generate_single_plan(plan_messages, self.plan_temperature, config, 0)
    
    async def _generate_single_plan(self, messages, temperature, config, retry_cnt):
        """生成单个计划"""
        result = await astream(
            self.llm,
            messages,
            {"thinking": {"type": "enabled"}, "temperature": temperature},
            config=config
        )
        response_content = result.content
        
        try:
            curr_plan = json.loads(repair_json_output(response_content))
            curr_plan = Plan.model_validate(curr_plan)
            
            if len(curr_plan.steps) > self.max_steps and retry_cnt < self.max_retry_count:
                messages.append({
                    "role": "user",
                    "content": f"Limit the plan to a maximum of {self.max_steps} steps, regenerate the plan."
                })
                return await self._generate_single_plan(messages, temperature, config, retry_cnt + 1)
            
            return curr_plan
        except Exception as e:
            logger.warning(f"Plan parsing error: {str(e)}")
            if retry_cnt < self.max_retry_count:
                messages.append({"role": "user", "content": "Not a valid plan, regenerate the plan."})
                return await self._generate_single_plan(messages, temperature, config, retry_cnt + 1)
        return response_content
    
    async def _decide_report_or_end(self, state, last_plan, executed_steps, user_question):
        """决定是生成报告还是直接结束"""
        chart_count = 0
        for step in executed_steps:
            if hasattr(step, 'summary_execution_res'):
                res = step.summary_execution_res
                if (isinstance(res, dict) and 'chart_path' in res) or \
                   (isinstance(res, str) and 'chart_path' in res):
                    chart_count += 1
        
        try:
            intent_result = self.report_intent_recognizer.recognize(
                user_question=user_question,
                executed_steps=len(executed_steps),
                chart_count=chart_count
            )
            
            if intent_result.should_generate_report:
                return Command(
                    update={
                        "current_plan": last_plan,
                        "executed_steps": executed_steps,
                        "replan_cnt": state.get("replan_cnt"),
                        "should_generate_report": True,
                        "report_intent_confidence": intent_result.confidence_score,
                        "report_decision_reason": intent_result.decision_reason
                    },
                    goto="report_agent"
                )
            else:
                await self._present_results_directly(executed_steps, state)
                return Command(
                    update={
                        "current_plan": last_plan,
                        "executed_steps": executed_steps,
                        "replan_cnt": state.get("replan_cnt"),
                        "should_generate_report": False,
                        "report_intent_confidence": intent_result.confidence_score,
                        "report_decision_reason": intent_result.decision_reason
                    },
                    goto="__end__"
                )
        except Exception as e:
            logger.error(f"Error in report intent recognition: {str(e)}", exc_info=True)
            return Command(
                update={
                    "current_plan": last_plan,
                    "executed_steps": executed_steps,
                    "replan_cnt": state.get("replan_cnt")
                },
                goto="report_agent"
            )
    
    async def _present_results_directly(self, executed_steps, state):
        """直接呈现结果"""
        from langchain_core.messages import AIMessage
        
        result_messages = []
        all_code_files = []
        
        for i, step in enumerate(executed_steps):
            step_title = step.title if hasattr(step, 'title') else f"Step {i+1}"
            
            # 提取步骤结果
            step_result = "No result"
            if hasattr(step, 'summary_execution_res') and step.summary_execution_res:
                step_result = step.summary_execution_res
            elif hasattr(step, 'execution_res') and step.execution_res:
                step_result = step.execution_res
            
            # 尝试从结果中提取有意义的内容
            formatted_result = self._extract_meaningful_result(step_result)
            
            result_msg = f"### {step_title}\n\n{formatted_result}"
            result_messages.append(result_msg)
            
            # 收集生成的代码文件
            if hasattr(step, 'generated_code_files'):
                all_code_files.extend(step.generated_code_files)
        
        # 如果有生成的代码文件，添加到结果中
        if all_code_files:
            code_section = "\n\n---\n\n## 🐍 生成的Python代码\n\n"
            for i, code_file in enumerate(all_code_files):
                filename = code_file.get('filename', f'script_{i+1}.py')
                code_content = code_file.get('code_content', '')
                code_section += f"### {filename}\n```python\n{code_content}\n```\n\n"
            result_messages.append(code_section)
        
        if result_messages:
            combined_result = "\n\n---\n\n".join(result_messages)
            push_message(AIMessage(
                content=combined_result,
                id=f"direct-result-{str(uuid.uuid4())}"
            ))
            
            history = state.get("history", [])
            history.append({"role": "assistant", "content": combined_result})
    
    def _extract_meaningful_result(self, result):
        """从结果中提取有意义的内容"""
        if not result:
            return "No result"
        
        # 如果是字符串，直接返回
        if isinstance(result, str):
            return result
        
        # 如果是列表，尝试格式化
        if isinstance(result, list):
            formatted_items = []
            for item in result:
                if isinstance(item, dict):
                    # 尝试从字典中提取有用的信息
                    if 'result' in item:
                        formatted_items.append(str(item['result']))
                    elif 'execution_result' in item:
                        formatted_items.append(str(item['execution_result']))
                    elif 'terminate' in item:
                        continue  # 跳过terminate信息
                    else:
                        formatted_items.append(str(item))
                else:
                    formatted_items.append(str(item))
            return "\n".join(formatted_items) if formatted_items else str(result)
        
        # 如果是字典
        if isinstance(result, dict):
            # 尝试提取有用的字段
            if 'result' in result:
                return str(result['result'])
            elif 'execution_result' in result:
                return str(result['execution_result'])
            elif 'data_summary' in result:
                return str(result['data_summary'])
            else:
                return json.dumps(result, ensure_ascii=False, indent=2)
        
        # 其他情况，转换为字符串
        return str(result)
    
    def _parse_and_add_sub_steps(self, execution_record: StepExecutionRecord, results):
        """从结果中解析并添加子步骤到执行记录中"""
        if not results:
            return
        
        # 处理列表类型的结果
        if isinstance(results, list):
            for i, item in enumerate(results):
                if isinstance(item, dict):
                    self._add_sub_step_from_dict(execution_record, item, i)
    
    def _add_sub_step_from_dict(self, execution_record: StepExecutionRecord, item: dict, index: int):
        """从字典中创建子步骤"""
        try:
            # 尝试提取子步骤信息
            step_name = item.get('tool_called', f"Sub-step {index + 1}")
            tool_used = "unknown"
            
            # 从tool_called中提取工具名称
            if 'tool_called' in item:
                tool_used = item['tool_called']
            elif 'tool_name' in item:
                tool_used = item['tool_name']
            
            # 提取结果
            result = item.get('result', item.get('execution_result', item))
            
            # 创建子步骤记录
            sub_step = StepExecutionRecord(
                step_name=step_name,
                tool_used=tool_used,
                execution_status=ExecutionStatus.SUCCESS,
                result=result
            )
            sub_step.mark_complete(ExecutionStatus.SUCCESS, result)
            
            # 添加到父步骤
            execution_record.add_sub_step(sub_step)
            
        except Exception as e:
            logger.warning(f"Failed to parse sub-step from dict: {str(e)}")
