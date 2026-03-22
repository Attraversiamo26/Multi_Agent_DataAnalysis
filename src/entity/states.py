from typing import Annotated, List, Dict, Optional, Any
import operator
from langgraph.graph import MessagesState
from dataclasses import dataclass, field
from datetime import datetime

from src.entity.planner_model import Plan, Step


@dataclass
class StandardOutput:
    """Standard output structure for all agents"""
    success: bool = True
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SearchResult(StandardOutput):
    """Standard output for SearchAgent - 问数结果"""
    query_type: str = ""  # "average", "comparison", "summary", "count"
    data_summary: Dict[str, Any] = field(default_factory=dict)
    raw_data: Optional[str] = None
    statistics: Dict[str, float] = field(default_factory=dict)


@dataclass
class AnalysisResult(StandardOutput):
    """Standard output for AnalysisAgent - 分析建模结果"""
    analysis_type: str = ""  # "correlation", "regression", "clustering", "trend", "multi_factor"
    generated_code: str = ""
    code_executed: bool = False
    execution_result: Optional[str] = None
    model_metrics: Dict[str, Any] = field(default_factory=dict)
    insights: List[str] = field(default_factory=list)


@dataclass
class VisualizationResult(StandardOutput):
    """Standard output for VisualizationAgent - 可视化结果"""
    chart_type: str = ""  # "bar", "line", "pie", "radar", "scatter", "heatmap"
    chart_title: str = ""
    chart_path: Optional[str] = None
    chart_base64: Optional[str] = None
    variables_used: List[str] = field(default_factory=list)
    chart_description: str = ""
    generated_code: str = ""


@dataclass
class ReportResult(StandardOutput):
    """Standard output for ReportAgent - 报告结果"""
    report_format: str = ""  # "md", "word", "csv"
    report_path: Optional[str] = None
    report_content: str = ""
    sections_included: List[str] = field(default_factory=list)
    word_count: int = 0


class PlanState(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = ""
    ask_user_question: str = None
    current_plan: Plan | str = None
    # Use Annotated with reducer to handle concurrent updates
    history: Annotated[List[Dict], operator.add] = []
    user_question: str = ""
    origin_user_question: str = ""
    replan_cnt: int = 0
    executed_steps: List[Step] = []
    workspace_directory: str = ""
    retrieved_info: str = ""
    need_replan: bool = True
    
    # Intent Recognition - Enhanced
    intent: str = ""
    intent_confidence: float = 0.0
    intent_type: str = ""  # "ASK_DATA", "ANALYSIS_MODELING", "VISUALIZATION", "REPORT", "SMALLTALK"
    
    # Standardized Agent Outputs 
    search_result: Optional[SearchResult] = None
    analysis_result: Optional[AnalysisResult] = None
    visualization_result: Optional[VisualizationResult] = None
    report_result: Optional[ReportResult] = None
    
    # Legacy fields (backward compatibility)
    generated_code: str = ""
    code_execution_result: str = ""
    modeling_result: str = ""
    
    # Report Generation Workflow
    should_generate_report: Optional[bool] = None
    report_intent_confidence: Optional[float] = None
    report_decision_reason: Optional[str] = None
    report_format: str = "md"  # "md", "word", "csv"
    report_outline: str = ""
    
    # Report Planning
    report_requirements: str = ""  # 用户的报告大纲要求
    analysis_plan: str = ""  # 根据大纲生成的分析计划
    visualization_plan: str = ""  # 根据大纲生成的可视化计划
    
    # Workflow State Tracking
    analysis_completed: bool = False
    visualization_completed: bool = False
    report_planning_completed: bool = False
    report_phase: str = ""  # "planning", "analysis", "visualization", "final"


class StepState(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = ""
    # Use Annotated with reducer to handle concurrent updates
    history: Annotated[List[Dict], operator.add] = []
    execute_res: str = None
    workspace_directory: str = ""
    current_step: Step = None