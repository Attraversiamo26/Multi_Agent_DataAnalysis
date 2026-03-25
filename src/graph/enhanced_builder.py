import logging
from typing import Dict, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START
from langgraph.types import interrupt, Command

from src.entity.states import PlanState
from src.entity.enhanced_states import StepExecutionRecord, ExecutionStatus
from src.utils.agent_utils import _initialize_agents
from src.llms.llm import get_llm_by_name
from src.utils.llm_utils import astream

logger = logging.getLogger(__name__)


def ask_user_node(state: PlanState):
    """询问用户节点"""
    ask_user_question = state["ask_user_question"]
    feedback = interrupt(ask_user_question)

    answer = str(feedback.get('data'))
    if answer.lower() == 'continue':
        return Command(
            update={
                "need_replan": False
            },
            goto="plan_agent"
        )
    else:
        update_messages = [{"role": "user", "content": f"Regarding the question of [{ask_user_question}], my answer is: {answer}"}]
        return Command(
            update={
                "history": state["history"] + update_messages,
            },
            goto="plan_agent"
        )


def route_based_on_intent(state: PlanState):
    """基于增强的意图识别结果进行路由"""
    intent_type = state.get("intent_type", "")
    
    logger.info(f"Routing based on intent: {intent_type}")
    
    if intent_type == "SMALLTALK":
        return "small_talk_agent"
    elif intent_type == "REPORT":
        return "report_workflow_router"
    else:
        # 所有分析任务都通过plan_agent生成完整的执行计划
        return "plan_agent"


def report_workflow_router(state: PlanState):
    """报告生成工作流的路由器 - 先计划，再分析，再可视化，最后报告"""
    report_phase = state.get("report_phase", "")
    report_planning_completed = state.get("report_planning_completed", False)
    analysis_completed = state.get("analysis_completed", False)
    visualization_completed = state.get("visualization_completed", False)
    
    logger.info(f"Report workflow routing - phase: {report_phase}, planning_done: {report_planning_completed}, "
               f"analysis_done: {analysis_completed}, viz_done: {visualization_completed}")
    
    if report_phase == "":
        return "start_report_workflow"
    elif not report_planning_completed:
        return "plan_report_requirements"
    elif not analysis_completed:
        return "analysis_agent"
    elif not visualization_completed:
        return "visualization_agent"
    else:
        return "report_agent"


def start_report_workflow(state: PlanState):
    """初始化报告生成工作流"""
    user_question = state.get("user_question", "")
    logger.info(f"Starting report workflow for: {user_question}")
    
    return Command(
        update={
            "report_phase": "planning",
            "report_planning_completed": False,
            "analysis_completed": False,
            "visualization_completed": False,
            "report_requirements": user_question
        },
        goto="plan_report_requirements"
    )


async def plan_report_requirements(state: PlanState, config):
    """根据用户的报告大纲计划分析和可视化需求"""
    from langchain_core.runnables import RunnableConfig
    
    llm = get_llm_by_name("plan_agent")
    report_requirements = state.get("report_requirements", "")
    user_question = state.get("user_question", "")
    
    logger.info(f"Planning report requirements: {report_requirements}")
    
    planning_prompt = f"""
            You are a senior data analyst. Based on the user's report requirements, please create:
            1. A detailed analysis plan - what statistical analysis and modeling should be performed
            2. A detailed visualization plan - what charts and visualizations should be created

            ## User's Report Requirements
            {report_requirements}

            ## Original Question
            {user_question}

            Please output in the following JSON format:
            ```json
            {{
            "analysis_plan": "Detailed description of what analysis to perform (correlation, regression, clustering, etc.)",
            "visualization_plan": "Detailed description of what visualizations to create (bar charts, line charts, scatter plots, etc.)",
            "report_outline": "Proposed outline for the final report"
            }}
            ```
"""
    
    messages = [{"role": "user", "content": planning_prompt}]
    result = await astream(llm, messages, {"thinking": {"type": "enabled"}}, config)
    
    import json
    import re
    
    try:
        json_match = re.search(r'\{[\s\S]*\}', result.content)
        if json_match:
            plan_data = json.loads(json_match.group(0))
            analysis_plan = plan_data.get("analysis_plan", "")
            visualization_plan = plan_data.get("visualization_plan", "")
            report_outline = plan_data.get("report_outline", "")
        else:
            analysis_plan = "Perform comprehensive statistical analysis"
            visualization_plan = "Create appropriate visualizations"
            report_outline = ""
    except:
        analysis_plan = "Perform comprehensive statistical analysis"
        visualization_plan = "Create appropriate visualizations"
        report_outline = ""
    
    return Command(
        update={
            "analysis_plan": analysis_plan,
            "visualization_plan": visualization_plan,
            "report_outline": report_outline,
            "report_planning_completed": True,
            "report_phase": "analysis"
        },
        goto="analysis_agent"
    )


def after_analysis_router(state: PlanState):
    """分析Agent完成后的路由"""
    logger.info("Analysis completed, routing to visualization")
    
    # 添加执行记录
    execution_record = StepExecutionRecord(
        step_name="数据分析",
        tool_used="analysis_agent",
        execution_status=ExecutionStatus.SUCCESS,
        result=state.get("analysis_result")
    )
    execution_record.mark_complete(ExecutionStatus.SUCCESS)
    
    return Command(
        update={
            "analysis_completed": True,
            "report_phase": "visualization"
        },
        goto="visualization_agent"
    )


def after_visualization_router(state: PlanState):
    """可视化Agent完成后的路由"""
    logger.info("Visualization completed, routing to report generation")
    
    # 添加执行记录
    execution_record = StepExecutionRecord(
        step_name="数据可视化",
        tool_used="visualization_agent",
        execution_status=ExecutionStatus.SUCCESS,
        result=state.get("visualization_result")
    )
    execution_record.mark_complete(ExecutionStatus.SUCCESS)
    
    return Command(
        update={
            "visualization_completed": True,
            "report_phase": "final"
        },
        goto="report_agent"
    )


def create_step_execution_record(
    step_name: str,
    tool_used: str,
    status: ExecutionStatus,
    result: Any = None,
    error_message: str = None
) -> StepExecutionRecord:
    """创建步骤执行记录"""
    record = StepExecutionRecord(
        step_name=step_name,
        tool_used=tool_used,
        execution_status=status,
        result=result
    )
    record.mark_complete(status, result, error_message)
    return record


def _build_enhanced_graph():
    """构建增强版的状态图，包含所有节点和边"""
    agents = _initialize_agents()
    
    # 替换为增强版意图识别Agent
    from src.agents.enhanced_intent_recognition_agent import EnhancedIntentRecognitionAgent
    agents["intent_recognition_agent"] = EnhancedIntentRecognitionAgent(agent_name="intent_recognition_agent")
    
    builder = StateGraph(PlanState)

    # 添加所有Agent节点
    builder.add_node("intent_recognition_agent", agents["intent_recognition_agent"].run)
    builder.add_node("small_talk_agent", agents["small_talk_agent"].run)
    builder.add_node("report_agent", agents["report_agent"].run)
    builder.add_node("plan_agent", agents["plan_agent"].run)
    builder.add_node("analysis_agent", agents["analysis_agent"].run)
    builder.add_node("search_agent", agents["search_agent"].run)
    builder.add_node("visualization_agent", agents["visualization_agent"].run)
    builder.add_node("generate_agent", agents["generate_agent"].run)
    builder.add_node("manage_agent", agents["manage_agent"].run)
    builder.add_node("knowledge_agent", agents["knowledge_agent"].run)
    
    # 添加工作流节点
    builder.add_node("ask_user", ask_user_node)
    builder.add_node("start_report_workflow", start_report_workflow)
    builder.add_node("plan_report_requirements", plan_report_requirements)
    builder.add_node("after_analysis_router", after_analysis_router)
    builder.add_node("after_visualization_router", after_visualization_router)
    builder.add_node("report_workflow_router", report_workflow_router)

    # 添加边：从START到意图识别
    builder.add_edge(START, "intent_recognition_agent")
    
    # 添加条件边：从意图识别到相应的路由
    builder.add_conditional_edges(
        "intent_recognition_agent",
        route_based_on_intent,
        {
            "plan_agent": "plan_agent",
            "small_talk_agent": "small_talk_agent",
            "search_agent": "search_agent",
            "analysis_agent": "analysis_agent",
            "visualization_agent": "visualization_agent",
            "report_workflow_router": "report_workflow_router"
        }
    )
    
    # 添加条件边：报告工作流路由
    builder.add_conditional_edges(
        "report_workflow_router",
        report_workflow_router,
        {
            "start_report_workflow": "start_report_workflow",
            "plan_report_requirements": "plan_report_requirements",
            "analysis_agent": "analysis_agent",
            "visualization_agent": "visualization_agent",
            "report_agent": "report_agent"
        }
    )
    
    # 添加边：分析完成后路由
    builder.add_edge("analysis_agent", "after_analysis_router")
    # 添加边：可视化完成后路由
    builder.add_edge("visualization_agent", "after_visualization_router")

    logger.info("Enhanced graph built successfully")
    return builder


def build_enhanced_graph():
    """构建并返回增强版的graph"""
    memory = MemorySaver()
    builder = _build_enhanced_graph()
    return builder.compile(checkpointer=memory)
