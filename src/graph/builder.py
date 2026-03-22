from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START
from langgraph.types import interrupt, Command

from src.entity.states import PlanState
from src.utils.agent_utils import _initialize_agents
from src.llms.llm import get_llm_by_name
from src.utils.llm_utils import astream

def ask_user_node(state: PlanState):
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
        update_messages= [{"role": "user", "content": f"Regarding the question of [{ask_user_question}], my answer is: {answer}"}]
        return Command(
                update={
                    "history": state["history"] + update_messages,
                },
                goto="plan_agent"
            )

def route_based_on_intent(state: PlanState):
    """Route to appropriate agent based on enhanced intent recognition result"""
    intent_type = state.get("intent_type", "")
    
    if intent_type == "SMALLTALK":
        return "small_talk_agent"
    elif intent_type == "ASK_DATA":
        return "search_agent"
    elif intent_type == "ANALYSIS_MODELING":
        return "analysis_agent"
    elif intent_type == "VISUALIZATION":
        return "visualization_agent"
    elif intent_type == "REPORT":
        return "report_workflow_router"
    else:
        return "plan_agent"

def report_workflow_router(state: PlanState):
    """Router for report generation workflow - first plan, then analysis, then visualization, then report"""
    report_phase = state.get("report_phase", "")
    report_planning_completed = state.get("report_planning_completed", False)
    analysis_completed = state.get("analysis_completed", False)
    visualization_completed = state.get("visualization_completed", False)
    
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
    """Initialize report generation workflow"""
    user_question = state.get("user_question", "")
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
    """Plan analysis and visualization requirements based on user's report outline"""
    from langchain_core.runnables import RunnableConfig
    
    llm = get_llm_by_name("plan_agent")
    report_requirements = state.get("report_requirements", "")
    user_question = state.get("user_question", "")
    
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
    """Route after analysis agent completes"""
    return Command(
        update={
            "analysis_completed": True,
            "report_phase": "visualization"
        },
        goto="visualization_agent"
    )

def after_visualization_router(state: PlanState):
    """Route after visualization agent completes"""
    return Command(
        update={
            "visualization_completed": True,
            "report_phase": "final"
        },
        goto="report_agent"
    )

def _build_base_graph():
    """Build and return the optimized state graph with all nodes and edges, inspired by AutoSTAT architecture."""
    agents = _initialize_agents()
    builder = StateGraph(PlanState)

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
    builder.add_node("ask_user", ask_user_node)
    builder.add_node("start_report_workflow", start_report_workflow)
    builder.add_node("plan_report_requirements", plan_report_requirements)
    builder.add_node("after_analysis_router", after_analysis_router)
    builder.add_node("after_visualization_router", after_visualization_router)

    builder.add_edge(START, "intent_recognition_agent")
    
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
    
    builder.add_edge("analysis_agent", "after_analysis_router")
    builder.add_edge("visualization_agent", "after_visualization_router")

    return builder


def build_graph():
    memory = MemorySaver()
    builder = _build_base_graph()
    return builder.compile(checkpointer=memory)
