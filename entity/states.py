from typing import Annotated, List, Dict, Optional, Any
import operator
from langgraph.graph import MessagesState
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.entity.planner_model import Plan, Step


class ExecutionStatus(str, Enum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepExecutionRecord:
    """步骤执行记录，包含标准JSON格式输出"""
    step_name: str
    tool_used: str
    execution_status: ExecutionStatus
    result: Any
    purpose: Optional[str] = None
    methodology: Optional[str] = None
    expected_outcomes: Optional[str] = None
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    
    def to_json(self) -> Dict[str, Any]:
        """转换为标准JSON格式，只输出摘要信息"""
        def summarize_result(data):
            if data is None:
                return None
            if isinstance(data, str):
                return data
            if isinstance(data, (int, float, bool)):
                return data
            
            if hasattr(data, '__dataclass_fields__'):
                try:
                    result_dict = {}
                    for field_name in data.__dataclass_fields__:
                        try:
                            value = getattr(data, field_name)
                            result_dict[field_name] = summarize_result(value)
                        except Exception:
                            pass
                    return result_dict
                except Exception:
                    return str(data)
            
            if isinstance(data, list):
                if len(data) == 0:
                    return []
                processed_items = [summarize_result(item) for item in data]
                if len(processed_items) > 5:
                    return f"[List with {len(processed_items)} items - showing first 5]: {processed_items[:5]}"
                return processed_items
            
            if isinstance(data, dict):
                summarized = {}
                for key, value in data.items():
                    if any(keyword in str(key).lower() for keyword in ['data', 'columns', 'values', 'records']):
                        if isinstance(value, (list, dict)) and len(str(value)) > 500:
                            summarized[key] = f"[Summary] {type(value).__name__} with {len(value) if hasattr(value, '__len__') else 'multiple'} items"
                        else:
                            summarized[key] = summarize_result(value)
                    else:
                        summarized[key] = summarize_result(value)
                return summarized
            
            str_data = str(data)
            if len(str_data) > 1000:
                return f"[Truncated] {str_data[:1000]}..."
            return str_data
        
        result = {
            "step_name": self.step_name,
            "tool_used": self.tool_used,
            "execution_status": self.execution_status.value if isinstance(self.execution_status, ExecutionStatus) else self.execution_status,
            "purpose": self.purpose,
            "methodology": self.methodology,
            "expected_outcomes": self.expected_outcomes,
            "result": summarize_result(self.result),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message
        }
        
        return result
    
    def mark_complete(self, status: ExecutionStatus, result: Any = None, error_message: str = None):
        """标记步骤完成"""
        self.end_time = datetime.now().isoformat()
        self.execution_status = status
        self.result = result
        self.error_message = error_message
        
        if self.start_time and self.end_time:
            try:
                start = datetime.fromisoformat(self.start_time)
                end = datetime.fromisoformat(self.end_time)
                self.duration_seconds = (end - start).total_seconds()
            except:
                pass


@dataclass
class GeneratedCodeFile:
    """生成的Python代码文件"""
    filename: str
    code_content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    executed: bool = False
    execution_result: Optional[str] = None
    
    def save_to_file(self, directory: str) -> str:
        """保存代码到文件"""
        import os
        os.makedirs(directory, exist_ok=True)
        file_path = os.path.join(directory, self.filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.code_content)
        return file_path
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "filename": self.filename,
            "code_content": self.code_content,
            "created_at": self.created_at,
            "executed": self.executed,
            "execution_result": self.execution_result
        }


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
    
    # Standard Execution Records 
    execution_records: Annotated[List[StepExecutionRecord], operator.add] = field(default_factory=list)
    
    # Generated Code Files
    generated_code_files: Annotated[List[GeneratedCodeFile], operator.add] = field(default_factory=list)
    
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
    
    # Global Execution Status (新增)
    overall_status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    
    @staticmethod
    def add_execution_record(state: dict, record: StepExecutionRecord):
        """添加执行记录到状态字典中"""
        if 'execution_records' not in state or state['execution_records'] is None:
            state['execution_records'] = []
        state['execution_records'].append(record)
    
    @staticmethod
    def add_generated_code(state: dict, code_file: GeneratedCodeFile):
        """添加生成的代码文件到状态字典中"""
        if 'generated_code_files' not in state or state['generated_code_files'] is None:
            state['generated_code_files'] = []
        state['generated_code_files'].append(code_file)
    
    @staticmethod
    def get_all_execution_records_json(state: dict) -> List[Dict[str, Any]]:
        """从状态字典中获取所有执行记录的JSON格式"""
        if 'execution_records' not in state or state['execution_records'] is None:
            return []
        return [record.to_json() for record in state['execution_records']]
    
    @staticmethod
    def mark_workflow_complete(state: dict, status: ExecutionStatus):
        """在状态字典中标记工作流完成"""
        state['overall_status'] = status
        state['end_time'] = datetime.now().isoformat()


class StepState(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = ""
    # Use Annotated with reducer to handle concurrent updates
    history: Annotated[List[Dict], operator.add] = []
    execute_res: str = None
    workspace_directory: str = ""
    current_step: Step = None