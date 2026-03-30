import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message
from langgraph.types import Command

from src.config.loader import load_yaml_config
from src.entity.states import PlanState
from src.llms.llm import get_llm_by_name
from src.entity.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.utils.output_utils import repair_json_output
from src.utils.llm_utils import astream
from src.utils.rag_helper import RAGHelper
from src.utils.tag_manager import tag_scope, MessageTag

logger = logging.getLogger(__name__)


class PlanAgent:

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.llm = get_llm_by_name(self.agent_name)
        self.extract_llm = get_llm_by_name("extract")
        
        # Load configuration from YAML file (will be refreshed on each run)
        self.config = None
        self.capabilities = None
        self.agent_capabilities = None
        self._load_config()
    
    def _load_config(self):
        """Load or reload configuration from YAML file."""
        self.config = load_yaml_config("conf.yaml")
        capabilities = self.config.get("agents", {}).get("capabilities", {})
        self.agent_capabilities = json.dumps(capabilities, ensure_ascii=False, indent=2)
        agent_config = self.config.get("app", {})
        
        # Configuration parameters for planning behavior
        self.max_steps = agent_config.get("max_steps", 6)
        self.max_retry_count = agent_config.get("max_retry_count", 3)
        self.plan_temperature = agent_config.get("plan_temperature", 1.0)

        # Initialize RAG helper for information retrieval
        self.rag_helper = RAGHelper(self.extract_llm)

    async def _generate_single_plan(self, messages, temperature, config, retry_cnt):
        """Generate a single plan with retry logic"""
        result = await astream(
            self.llm, 
            messages, 
            {"thinking": {"type": "enabled"}, "temperature": temperature}, 
            config=config
        )
        response_content = result.content
        logger.info(f"Temperature: {temperature}. Single plan generation response: {response_content}")

        try:
            curr_plan = json.loads(repair_json_output(response_content))
            logger.info(f"Parsed plan: {curr_plan}")
            curr_plan = Plan.model_validate(curr_plan)
            
            # Validate plan step count
            if len(curr_plan.steps) > self.max_steps:
                if retry_cnt < self.max_retry_count:
                    messages.append({
                        "role": "user", 
                        "content": f"Limit the plan to a maximum of {self.max_steps} steps, regenerate the plan."
                    })
                    return await self._generate_single_plan(messages, temperature, config, retry_cnt + 1)
            return curr_plan
        except Exception as e:
            logger.warning(f"Plan parsing error: {str(e)}")
            if retry_cnt < self.max_retry_count:
                messages.append({"role": "user", "content": f"Not a valid plan, regenerate the plan."})
                return await self._generate_single_plan(messages, temperature, config, retry_cnt + 1)
        return response_content

    def _analyze_agent_needs(self, plan: Plan):
        """分析计划需要哪些agent"""
        needs_search = False
        needs_analysis = False
        needs_visualization = False
        
        if plan and plan.steps:
            for step in plan.steps:
                agent_name = step.agent.lower()
                if "search" in agent_name:
                    needs_search = True
                elif "analysis" in agent_name:
                    needs_analysis = True
                elif "visualization" in agent_name:
                    needs_visualization = True
        
        return needs_search, needs_analysis, needs_visualization

    async def run(self, state: PlanState, config: RunnableConfig):
        """
        Plan Agent主入口 - 只做规划，不执行
        :param state: Current plan state
        :param config: Runnable configuration
        :return: Command for next step
        """
        logger.info(f"[PlanAgent] ===== PlanAgent.run() started =====")
        logger.info(f"[PlanAgent] state keys: {list(state.keys())}")
        
        # Reload configuration to get latest uploaded files
        self._load_config()
        logger.info(f"[PlanAgent] Configuration reloaded, checking data sources...")
        
        current_plan = state.get("current_plan")
        messages = state.get("history", [])
        retrieved_info = state.get("retrieved_info", "")
        user_question = state.get('user_question', "")
        
        # Generate initial plan if none exists
        if current_plan is None:
            with tag_scope(config, MessageTag.THINK):
                push_message(HumanMessage(
                    content=f"Analyzing the problem...", 
                    id=f"record-{str(uuid.uuid4())}"
                ))
                
                # Retrieve all relevant information using unified RAG helper
                try:
                    retrieved_info = await self.rag_helper.retrieve_information(
                        user_question, 
                        config
                    )
                except Exception as e:
                    logger.warning(f"Information retrieval failed: {str(e)}. Continuing without retrieval.")
                    retrieved_info = ""

            push_message(HumanMessage(
                content=f"Creating execution plan", 
                id=f"record-{str(uuid.uuid4())}"
            ))
            
            # Build prompt based on whether we have retrieved information
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
                user_prompt = f"""
             Create a plan to solve this question: {user_question}
            """

            messages.append({"role": "user", "content": user_prompt})
            
            # Generate plan
            input_ = {
                "messages": messages,
                "AGENT_CAPABILITIES": self.agent_capabilities,
                "locale": state.get("locale")
            }
            logger.info(f"messages: {messages}")
            plan_messages = apply_prompt_template(self.agent_name, input_)
            current_plan = await self._generate_single_plan(plan_messages, self.plan_temperature, config, 0)
            messages.append({"role": "assistant", "content": current_plan.model_dump_json()})

        # Ask user
        questions = current_plan.questions
        if len(questions) > 0:
            ask_user_question = ". \n".join([q.question for q in questions])
            return Command(
                update={
                    "current_plan": current_plan,
                    "history": [msg for msg in messages if msg['role'] != 'system'],
                    "retrieved_info": retrieved_info,
                    "ask_user_question": ask_user_question
                },
                goto="ask_user"
            )
        
        # 分析需要哪些agent
        needs_search, needs_analysis, needs_visualization = self._analyze_agent_needs(current_plan)
        
        logger.info(f"[PlanAgent] Plan analysis - needs_search: {needs_search}, "
                   f"needs_analysis: {needs_analysis}, needs_visualization: {needs_visualization}")
        
        # 规划完成，路由到plan_workflow_router
        return Command(
            update={
                "current_plan": current_plan,
                "history": [msg for msg in messages if msg['role'] != 'system'],
                "retrieved_info": retrieved_info,
                "needs_search": needs_search,
                "needs_analysis": needs_analysis,
                "needs_visualization": needs_visualization,
                "search_completed": False,
                "analysis_completed": False,
                "visualization_completed": False
            },
            goto="plan_workflow_router"
        )
