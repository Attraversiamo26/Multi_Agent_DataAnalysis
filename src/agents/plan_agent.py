import json
import logging
import traceback
import uuid

from langchain_core.messages import HumanMessage
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
from src.llms.llm import get_llm_by_name
from src.entity.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.utils.agent_utils import create_task_description_handoff_tool
from src.utils.output_utils import repair_json_output
from src.utils.llm_utils import astream
from src.utils.rag_helper import RAGHelper
from src.utils.tag_manager import tag_scope, MessageTag
from src.utils.report_intent_recognizer import ReportIntentRecognizer

logger = logging.getLogger(__name__)


class PlanAgent:

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
        
        # Initialize report intent recognizer
        self.report_intent_recognizer = ReportIntentRecognizer()
        
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
        self.max_replan_count = agent_config.get("max_replan_count", 10)
        self.plan_temperature = agent_config.get("plan_temperature", 1.0)

        # Initialize RAG helper for information retrieval
        self.rag_helper = RAGHelper(self.extract_llm)

    def _build_replan_context(self, current_plan, state):
        """Build context information needed for replanning"""
        context_parts = []

        # Add original user question
        context_parts.append(f"## Original User Question\n{state['user_question']}")

        # Add current plan status
        if current_plan and current_plan.steps:
            plan_info = f"## Current Plan\nTitle: {current_plan.title}\nThought: {current_plan.thought}\n"
            steps_info = []
            for i, step in enumerate(current_plan.steps):
                steps_info.append(f"  Step {i + 1}: {step.description} (agent: {step.agent})")
            plan_info += "\n".join(steps_info)
            context_parts.append(plan_info)

        # Add results of executed steps
        executed_steps = state.get('executed_steps', [])
        if executed_steps:
            executed_info = ["## Agent Execution Results"]
            for step in executed_steps:
                status_emoji = "✅" if step.final_status == "success" else "❌"
                result = step.summary_execution_res if step.summary_execution_res else step.execution_res
                executed_info.append(f"{status_emoji} Task: {step.description}\nAgent: {step.agent}\nResult: {result}")
            context_parts.append("\n\n".join(executed_info))

        return "\n\n".join(context_parts)

    def _build_plan_overview(self, state, user_question, current_plan, current_step_index):
        """Build a concise plan overview to help sub-agents understand the overall steps"""

        # Add results of executed steps (including all statuses: success, failure, etc.)
        executed_results = []
        for executed_step in state.get('executed_steps', []):
            status_emoji = "✅" if executed_step.final_status == "success" else "❌"
            result = executed_step.summary_execution_res if executed_step.summary_execution_res else executed_step.execution_res
            executed_results.append(f"{status_emoji} Task: {executed_step.description}\nAgent: {executed_step.agent}\nResult: {result}")

        # Build plan steps with status indicators
        plan_steps = []
        for i, step in enumerate(current_plan.steps):
            if i < current_step_index:
                # Completed steps
                plan_steps.append(f"  ✅ Step {i + 1} ({step.agent}): {step.description}")
            elif i == current_step_index:
                # Current step
                plan_steps.append(f"  ➡️ Step {i + 1} ({step.agent}): {step.description} [current task]")
            else:
                # Pending steps
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
        """Create execution instruction for the current step"""
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

    async def _replan(self, current_plan, messages, state, retrieved_info, config, retry_cnt):
        """Replan based on execution results"""
        logger.info(f"Replan messages: {messages}")

        # Build clear replanning context
        replan_context = self._build_replan_context(current_plan, state)

        # Build replanning instruction
        replan_instruction = f"""
## Retrieved Information        
------BEGIN------
{retrieved_info}
------END------

## Task Requirements
Update the plan based on the above information:
- If sufficient data exists to answer the user's question, terminate the plan (steps = [])
- Otherwise, create a new plan with only remaining steps (do not repeat completed steps)
- Check for data quality issues (approximations, incomplete data) and adjust if better methods exist
- Consider execution results, user feedback, and retrieved information
"""

        replan_msg = f"{replan_context}\n\n{replan_instruction}"
        messages.append({"role": "user", "content": replan_msg})
        input_ = {
            "messages": [msg for msg in messages if msg['role'] != 'system'],
            "AGENT_CAPABILITIES": self.agent_capabilities,
            "locale": state.get("locale")
        }
        replan_messages = apply_prompt_template("replan_agent", input_)
        result = await astream(self.llm, replan_messages, {"thinking": {"type": "enabled"}}, config=config)
        response_content = result.content
        logger.info(f"Replan response: {response_content}")
        messages.append({"role": "assistant", "content": response_content})
        
        try:
            replan = json.loads(repair_json_output(response_content))
            logger.info(f"Replan: {json.dumps(replan, ensure_ascii=False, indent=2)}")
            return Plan.model_validate(replan)
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.info(f"Replan again: {error_msg}")
            if retry_cnt < self.max_retry_count:
                messages.append({
                    "role": "user", 
                    "content": f"Invalid json output format detected. Please regenerate the plan. Error details: {error_msg}"
                })
                return await self._replan(current_plan, messages, state, retrieved_info, config, retry_cnt + 1)
            else:
                return response_content

    def _get_tool_for_agent(self, agent_name: str):
        """Get the appropriate tool for an agent by name"""
        tool_name = f"transfer_to_{agent_name}"
        matching_tools = [t for t in self.agent_tools if t.name == tool_name]
        if not matching_tools:
            raise ValueError(f"No tool found for agent: {agent_name}")
        return matching_tools[0]

    async def _process_step_execution_result(self, step, results, state, config):
        """Process and summarize execution results for a step"""
        if len(results) > 0:
            # Convert all results to text
            text_results = []
            for res in results:
                if isinstance(res, str):
                    text_results.append(res)
                else:
                    try:
                        text_results.append(json.dumps(res, ensure_ascii=False, indent=2))
                    except Exception:
                        text_results.append(str(res))
            step.execution_res = "\n".join(text_results)
            step.summary_execution_res = "\n".join(text_results)
            
            # Only compress results when execution results are lengthy
            if len(results) > 1:
                push_message(HumanMessage(
                    content="Summarizing execution results", 
                    id=f"record-{str(uuid.uuid4())}"
                ))
                
                input_ = {
                    "messages": [{
                        "role": "user", 
                        "content": f"""
Based on the following task information and `Execution Result`, please summarize the execution results of given task:

### Task Name
{step.title}

### Task Description
{step.description}

### Execution Result
{"\n".join(text_results)}
"""
                    }],
                    "locale": state.get("locale")
                }
                
                with tag_scope(config, MessageTag.SUMMARY):
                    summary_messages = apply_prompt_template("task_summary", input_)
                    result = await astream(
                        self.llm, 
                        summary_messages, 
                        {"thinking": {"type": "disabled"}}, 
                        config=config
                    )
                
                response_content = result.content
                logger.info(f"Summary response: {response_content}")
                step.summary_execution_res = response_content
        else:
            step.execution_res = "None"
            step.summary_execution_res = "None"

    async def _execute_plan_step(self, step, step_index, state, current_plan, config):
        """Execute a single plan step"""
        log_msg = f"""Executing step: {step.description}"""
        logger.info(log_msg)
        push_message(HumanMessage(content=log_msg, id=f"record-{str(uuid.uuid4())}"))

        # Build step context
        user_question = state['user_question']
        step_context = self._create_step_instruction(state, user_question, current_plan, step, step_index)

        # Get appropriate tool and execute
        tool = self._get_tool_for_agent(step.agent)
        res_dict = await tool.ainvoke({
            "messages": step_context,
            "workspace_directory": state["workspace_directory"],
            "current_step": step,
            "locale": state.get("locale"),
            "config": config
        })
        
        res = res_dict['execute_res']
        action_res, results = res
        
        # Update step status based on termination signal
        if action_res.get("terminate") is not None:
            terminate = action_res.get("terminate")
            if "success" in terminate:
                step.final_status = "success"
            elif "failure" in terminate:
                step.final_status = "failure"
        
        # Process execution results
        await self._process_step_execution_result(step, results, state, config)
        
        return step

    async def run(self, state: PlanState, config: RunnableConfig):
        """
        Main entry point for plan agent
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
        last_plan = current_plan
        executed_steps = state.get('executed_steps', [])
        messages = state.get("history", [])
        retrieved_info = state.get("retrieved_info", "")
        user_question = state.get('user_question', "")
        replan_cnt = state.get("replan_cnt", 0)
        need_replan = state.get("need_replan", True)
        
        logger.info(f"[PlanAgent] current_plan exists: {current_plan is not None}")
        logger.info(f"[PlanAgent] need_replan: {need_replan}")
        logger.info(f"[PlanAgent] replan_cnt: {replan_cnt}")
        logger.info(f"[PlanAgent] executed_steps count: {len(executed_steps)}")
        if current_plan and hasattr(current_plan, 'steps'):
            logger.info(f"[PlanAgent] current_plan.steps count: {len(current_plan.steps)}")

        # Handle replanning if plan already exists
        if current_plan is not None:
            if need_replan:
                push_message(HumanMessage(
                    content=f"Adjusting plan based on execution results",
                    id=f"record-{str(uuid.uuid4())}"
                ))

                if replan_cnt > self.max_replan_count:
                    push_message(HumanMessage(
                        content=f"Maximum replan attempts exceeded",
                        id=f"record-{str(uuid.uuid4())}"
                    ))
                    return Command(
                        update={},
                        goto="__end__",
                    )

                replan = await self._replan(current_plan, messages, state, retrieved_info, config, 0)
                current_plan = replan

        # Generate initial plan if none exists
        if current_plan is None:
            with tag_scope(config, MessageTag.THINK):
                push_message(HumanMessage(
                    content=f"Analyzing the problem...", 
                    id=f"record-{str(uuid.uuid4())}"
                ))
                
                # Retrieve all relevant information using unified RAG helper
                # This includes: agent data sources (CSV + database tables) + RAG documents
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
        # Execute plan steps
        if isinstance(current_plan, Plan) and len(current_plan.steps) > 0:
            logger.info(f"[PlanAgent] Starting step execution. Total steps: {len(current_plan.steps)}, Executed steps: {len(executed_steps)}")
            
            # Get the current step index based on how many steps have been executed
            current_step_index = len(executed_steps)
            logger.info(f"[PlanAgent] Current step index: {current_step_index}")
            
            # If there are still steps to execute
            if current_step_index < len(current_plan.steps):
                step = current_plan.steps[current_step_index]
                logger.info(f"[PlanAgent] Executing step {current_step_index + 1}/{len(current_plan.steps)}: {step.title} (agent: {step.agent})")
                
                # Execute current step
                try:
                    executed_step = await self._execute_plan_step(step, current_step_index, state, current_plan, config)
                    executed_steps.append(executed_step)
                    logger.info(f"[PlanAgent] Step {current_step_index + 1} completed. Total executed steps now: {len(executed_steps)}")
                except Exception as e:
                    logger.error(f"[PlanAgent] Error executing step {current_step_index + 1}: {str(e)}")
                    logger.error(traceback.format_exc())
                    raise
                
                # After each step, check if there are more steps
                if len(executed_steps) < len(current_plan.steps):
                    logger.info(f"[PlanAgent] More steps to execute ({len(executed_steps)}/{len(current_plan.steps)}), returning to plan_agent")
                    # More steps to execute, return to plan_agent
                    return Command(
                        update={
                            "current_plan": current_plan,
                            "executed_steps": executed_steps,
                            "replan_cnt": replan_cnt + 1,
                            "need_replan": False,  # Don't need to replan, just continue
                            "retrieved_info": retrieved_info
                        },
                        goto="plan_agent",
                    )
                else:
                    logger.info(f"[PlanAgent] All steps completed ({len(executed_steps)}/{len(current_plan.steps)}), checking report intent")
                    return await self._decide_report_or_end(state, last_plan, executed_steps, user_question)
            else:
                logger.info(f"[PlanAgent] All steps already completed, checking report intent")
                return await self._decide_report_or_end(state, last_plan, executed_steps, user_question)
        else:
            logger.info(f"[PlanAgent] No more steps, checking report intent")
            return await self._decide_report_or_end(state, last_plan, executed_steps, user_question)
    
    async def _decide_report_or_end(self, state, last_plan, executed_steps, user_question):
        """Decide whether to generate a report or end directly with results"""
        
        # Count charts from executed steps
        chart_count = 0
        for step in executed_steps:
            if hasattr(step, 'summary_execution_res'):
                res = step.summary_execution_res
                if isinstance(res, dict) and 'chart_path' in res:
                    chart_count += 1
                elif isinstance(res, str) and 'chart_path' in res:
                    chart_count += 1
        
        # Recognize report intent
        try:
            intent_result = self.report_intent_recognizer.recognize(
                user_question=user_question,
                executed_steps=len(executed_steps),
                chart_count=chart_count
            )
            
            logger.info(f"[PlanAgent] Report intent decision: should_generate_report={intent_result.should_generate_report}, "
                       f"confidence={intent_result.confidence_score:.2f}, "
                       f"reason='{intent_result.decision_reason}'")
            
            if intent_result.should_generate_report:
                # Need to generate report
                logger.info(f"[PlanAgent] Going to report_agent to generate comprehensive report")
                return Command(
                    update={
                        "current_plan": last_plan,
                        "executed_steps": executed_steps,
                        "replan_cnt": state.get("replan_cnt"),
                        "should_generate_report": True,
                        "report_intent_confidence": intent_result.confidence_score,
                        "report_decision_reason": intent_result.decision_reason
                    },
                    goto="report_agent",
                )
            else:
                # No need for report, present results directly
                logger.info(f"[PlanAgent] Skipping report_agent, presenting results directly")
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
                    goto="__end__",
                )
        except Exception as e:
            logger.error(f"[PlanAgent] Error in report intent recognition: {str(e)}", exc_info=True)
            logger.warning(f"[PlanAgent] Falling back to report_agent")
            return Command(
                update={
                    "current_plan": last_plan,
                    "executed_steps": executed_steps,
                    "replan_cnt": state.get("replan_cnt")
                },
                goto="report_agent",
            )
    
    async def _present_results_directly(self, executed_steps, state):
        """Present execution results directly in conversation without report generation"""
        from langchain_core.messages import AIMessage
        
        logger.info(f"[PlanAgent] Presenting {len(executed_steps)} step results directly")
        
        result_messages = []
        
        for i, step in enumerate(executed_steps):
            step_title = step.title if hasattr(step, 'title') else f"Step {i+1}"
            step_result = step.summary_execution_res if hasattr(step, 'summary_execution_res') else "No result"
            
            result_msg = f"### {step_title}\n\n{step_result}"
            result_messages.append(result_msg)
        
        if result_messages:
            combined_result = "\n\n---\n\n".join(result_messages)
            
            push_message(AIMessage(
                content=combined_result,
                id=f"direct-result-{str(uuid.uuid4())}"
            ))
            
            # Update history with the direct result
            history = state.get("history", [])
            history.append({"role": "assistant", "content": combined_result})
            
            logger.info(f"[PlanAgent] Direct results presented successfully")
