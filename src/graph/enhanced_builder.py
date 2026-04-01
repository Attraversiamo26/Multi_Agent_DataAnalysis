import logging
from typing import Dict, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START
from langgraph.types import interrupt, Command

from src.entity.states import PlanState, StepExecutionRecord, ExecutionStatus
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


def plan_workflow_router(state: PlanState):
    """计划工作流的路由器 - 支持选择性调用"""
    needs_search = state.get("needs_search", False)
    needs_analysis = state.get("needs_analysis", False)
    needs_visualization = state.get("needs_visualization", False)
    search_completed = state.get("search_completed", False)
    analysis_completed = state.get("analysis_completed", False)
    visualization_completed = state.get("visualization_completed", False)
    
    logger.info(f"Plan workflow routing - needs_search: {needs_search}, needs_analysis: {needs_analysis}, "
               f"needs_visualization: {needs_visualization}, search_done: {search_completed}, "
               f"analysis_done: {analysis_completed}, viz_done: {visualization_completed}")
    
    if needs_search and not search_completed:
        return Command(update={}, goto="plan_search_agent")
    elif needs_analysis and not analysis_completed:
        return Command(update={}, goto="plan_analysis_agent")
    elif needs_visualization and not visualization_completed:
        return Command(update={}, goto="plan_visualization_agent")
    else:
        return Command(update={}, goto="result_output_agent")


def report_workflow_router(state: PlanState):
    """报告生成工作流的路由器 - 支持选择性调用"""
    report_phase = state.get("report_phase", "")
    report_planning_completed = state.get("report_planning_completed", False)
    search_completed = state.get("search_completed", False)
    analysis_completed = state.get("analysis_completed", False)
    visualization_completed = state.get("visualization_completed", False)
    needs_search = state.get("needs_search", True)
    needs_analysis = state.get("needs_analysis", True)
    needs_visualization = state.get("needs_visualization", True)
    
    logger.info(f"Report workflow routing - phase: {report_phase}, planning_done: {report_planning_completed}, "
               f"search_done: {search_completed}, analysis_done: {analysis_completed}, viz_done: {visualization_completed}, "
               f"needs_search: {needs_search}, needs_analysis: {needs_analysis}, needs_visualization: {needs_visualization}")
    
    if report_phase == "":
        return Command(update={}, goto="start_report_workflow")
    elif not report_planning_completed:
        return Command(update={}, goto="plan_report_requirements")
    elif needs_search and not search_completed:
        return Command(update={}, goto="report_search_agent")
    elif needs_analysis and not analysis_completed:
        return Command(update={}, goto="report_analysis_agent")
    elif needs_visualization and not visualization_completed:
        return Command(update={}, goto="report_visualization_agent")
    else:
        return Command(update={}, goto="report_agent")


def start_report_workflow(state: PlanState):
    """初始化报告生成工作流"""
    user_question = state.get("user_question", "")
    logger.info(f"Starting report workflow for: {user_question}")
    
    return Command(
        update={
            "report_phase": "planning",
            "report_planning_completed": False,
            "search_completed": False,
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
            1. A detailed search plan - what data search and retrieval should be performed (if any)
            2. A detailed analysis plan - what statistical analysis and modeling should be performed
            3. A detailed visualization plan - what charts and visualizations should be created
            4. Whether search, analysis, and/or visualization are needed

            ## User's Report Requirements
            {report_requirements}

            ## Original Question
            {user_question}

            Please output in the following JSON format:
            ```json
            {{
            "search_plan": "Detailed description of what search/retrieval to perform (if any)",
            "analysis_plan": "Detailed description of what analysis to perform (correlation, regression, clustering, etc.)",
            "visualization_plan": "Detailed description of what visualizations to create (bar charts, line charts, scatter plots, etc.)",
            "report_outline": "Proposed outline for the final report",
            "needs_search": true,
            "needs_analysis": true,
            "needs_visualization": true
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
            search_plan = plan_data.get("search_plan", "")
            analysis_plan = plan_data.get("analysis_plan", "")
            visualization_plan = plan_data.get("visualization_plan", "")
            report_outline = plan_data.get("report_outline", "")
            needs_search = plan_data.get("needs_search", True)
            needs_analysis = plan_data.get("needs_analysis", True)
            needs_visualization = plan_data.get("needs_visualization", True)
        else:
            search_plan = "Perform necessary data search and retrieval"
            analysis_plan = "Perform comprehensive statistical analysis"
            visualization_plan = "Create appropriate visualizations"
            report_outline = ""
            needs_search = True
            needs_analysis = True
            needs_visualization = True
    except:
        search_plan = "Perform necessary data search and retrieval"
        analysis_plan = "Perform comprehensive statistical analysis"
        visualization_plan = "Create appropriate visualizations"
        report_outline = ""
        needs_search = True
        needs_analysis = True
        needs_visualization = True
    
    return Command(
        update={
            "search_plan": search_plan,
            "analysis_plan": analysis_plan,
            "visualization_plan": visualization_plan,
            "report_outline": report_outline,
            "report_planning_completed": True,
            "needs_search": needs_search,
            "needs_analysis": needs_analysis,
            "needs_visualization": needs_visualization,
            "search_completed": False,
            "analysis_completed": False,
            "visualization_completed": False,
            "report_phase": "search"
        },
        goto="report_workflow_router"
    )


async def report_search_agent_wrapper(state: PlanState, config):
    """报告工作流中搜索Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.search_agent import SearchAgent
    agent = SearchAgent(agent_name="search_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "search_completed": True,
            "report_phase": "search_done"
        },
        goto="report_workflow_router"
    )


async def report_analysis_agent_wrapper(state: PlanState, config):
    """报告工作流中分析Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.analysis_agent import AnalysisAgent
    agent = AnalysisAgent(agent_name="analysis_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "analysis_completed": True,
            "report_phase": "analysis_done"
        },
        goto="report_workflow_router"
    )


async def report_visualization_agent_wrapper(state: PlanState, config):
    """报告工作流中可视化Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.visualization_agent import VisualizationAgent
    agent = VisualizationAgent(agent_name="visualization_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "visualization_completed": True,
            "report_phase": "visualization_done"
        },
        goto="report_workflow_router"
    )


async def plan_search_agent_wrapper(state: PlanState, config):
    """计划工作流中搜索Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.search_agent import SearchAgent
    agent = SearchAgent(agent_name="search_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "search_completed": True
        },
        goto="plan_workflow_router"
    )


async def plan_analysis_agent_wrapper(state: PlanState, config):
    """计划工作流中分析Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.analysis_agent import AnalysisAgent
    agent = AnalysisAgent(agent_name="analysis_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "analysis_completed": True
        },
        goto="plan_workflow_router"
    )


async def plan_visualization_agent_wrapper(state: PlanState, config):
    """计划工作流中可视化Agent的包装器 - 完成后更新状态并返回router"""
    from src.agents.visualization_agent import VisualizationAgent
    agent = VisualizationAgent(agent_name="visualization_agent")
    await agent.run(state, config)
    
    return Command(
        update={
            "visualization_completed": True
        },
        goto="plan_workflow_router"
    )


def _build_enhanced_graph():
    """构建增强版的状态图，包含所有节点和边"""
    agents = _initialize_agents()
    
    # 替换为增强版意图识别Agent
    from src.agents.enhanced_intent_recognition_agent import EnhancedIntentRecognitionAgent
    agents["intent_recognition_agent"] = EnhancedIntentRecognitionAgent(agent_name="intent_recognition_agent")
    
    builder = StateGraph(PlanState)

    # 添加所有 Agent 节点
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
    
    # 添加结果输出 Agent（统一整合所有结果）
    from src.agents.result_output_agent import ResultOutputAgent
    agents["result_output_agent"] = ResultOutputAgent(agent_name="result_output_agent")
    builder.add_node("result_output_agent", agents["result_output_agent"].run)
    
    # 添加工作流节点
    builder.add_node("ask_user", ask_user_node)
    builder.add_node("start_report_workflow", start_report_workflow)
    builder.add_node("plan_report_requirements", plan_report_requirements)
    builder.add_node("report_workflow_router", report_workflow_router)
    builder.add_node("report_search_agent", report_search_agent_wrapper)
    builder.add_node("report_analysis_agent", report_analysis_agent_wrapper)
    builder.add_node("report_visualization_agent", report_visualization_agent_wrapper)
    builder.add_node("plan_workflow_router", plan_workflow_router)
    builder.add_node("plan_search_agent", plan_search_agent_wrapper)
    builder.add_node("plan_analysis_agent", plan_analysis_agent_wrapper)
    builder.add_node("plan_visualization_agent", plan_visualization_agent_wrapper)

    # 添加边：从START到意图识别
    builder.add_edge(START, "intent_recognition_agent")
    
    # 添加条件边：从意图识别到相应的路由
    builder.add_conditional_edges(
        "intent_recognition_agent",
        route_based_on_intent,
        {
            "plan_agent": "plan_agent",
            "small_talk_agent": "small_talk_agent",
            "report_workflow_router": "report_workflow_router"
        }
    )
    
    # 注意：plan_workflow_router和report_workflow_router通过Command对象直接指定跳转目标，不需要条件边
    
    # 重构：所有执行路径都汇聚到 result_output_agent
    # 1. plan_agent 完成后 → plan_workflow_router
    builder.add_edge("plan_agent", "plan_workflow_router")
    
    # 2. 报告 Agent 完成后 → result_output_agent → END
    builder.add_edge("report_agent", "result_output_agent")
    
    # 3. 闲聊 Agent 直接到 END（不需要整合结果）
    builder.add_edge("small_talk_agent", "__end__")
    
    # 4. result_output_agent → END
    builder.add_edge("result_output_agent", "__end__")

    logger.info("Enhanced graph built successfully")
    return builder


def build_enhanced_graph():
    """构建并返回增强版的graph"""
    memory = MemorySaver()
    builder = _build_enhanced_graph()
    return builder.compile(checkpointer=memory)
