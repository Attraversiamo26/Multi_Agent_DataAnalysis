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
    """步骤执行记录，包含标准JSON格式输出，支持嵌套子步骤"""
    step_name: str
    tool_used: str
    execution_status: ExecutionStatus
    result: Any
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    sub_steps: List['StepExecutionRecord'] = field(default_factory=list)
    
    def to_json(self) -> Dict[str, Any]:
        """转换为标准JSON格式，包含嵌套子步骤"""
        result = {
            "step_name": self.step_name,
            "tool_used": self.tool_used,
            "execution_status": self.execution_status.value if isinstance(self.execution_status, ExecutionStatus) else self.execution_status,
            "result": self.result,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message
        }
        
        # 添加嵌套的子步骤
        if self.sub_steps:
            result["sub_steps"] = [sub_step.to_json() for sub_step in self.sub_steps]
        
        return result
    
    def add_sub_step(self, sub_step: 'StepExecutionRecord'):
        """添加子步骤"""
        self.sub_steps.append(sub_step)
    
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


class EnhancedPlanState(MessagesState):
    """增强版计划状态，包含更完整的执行跟踪"""
    
    # 运行时变量
    locale: str = ""
    ask_user_question: str = None
    current_plan: Plan | str = None
    history: Annotated[List[Dict], operator.add] = []
    user_question: str = ""
    origin_user_question: str = ""
    replan_cnt: int = 0
    executed_steps: List[Step] = []
    workspace_directory: str = ""
    retrieved_info: str = ""
    need_replan: bool = True
    
    # 意图识别 - 增强版
    intent: str = ""
    intent_confidence: float = 0.0
    intent_type: str = ""
    
    # 标准执行记录
    execution_records: Annotated[List[StepExecutionRecord], operator.add] = field(default_factory=list)
    
    # 生成的代码文件
    generated_code_files: Annotated[List[GeneratedCodeFile], operator.add] = field(default_factory=list)
    
    # 标准化Agent输出
    search_result: Optional[Any] = None
    analysis_result: Optional[Any] = None
    visualization_result: Optional[Any] = None
    report_result: Optional[Any] = None
    
    # 旧字段（向后兼容）
    generated_code: str = ""
    code_execution_result: str = ""
    modeling_result: str = ""
    
    # 报告生成工作流
    should_generate_report: Optional[bool] = None
    report_intent_confidence: Optional[float] = None
    report_decision_reason: Optional[str] = None
    report_format: str = "md"
    report_outline: str = ""
    
    # 报告计划
    report_requirements: str = ""
    analysis_plan: str = ""
    visualization_plan: str = ""
    
    # 工作流状态跟踪
    analysis_completed: bool = False
    visualization_completed: bool = False
    report_planning_completed: bool = False
    report_phase: str = ""
    
    # 全局执行状态
    overall_status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    
    def add_execution_record(self, record: StepExecutionRecord):
        """添加执行记录"""
        if not hasattr(self, 'execution_records') or self.execution_records is None:
            self.execution_records = []
        self.execution_records.append(record)
    
    def add_generated_code(self, code_file: GeneratedCodeFile):
        """添加生成的代码文件"""
        if not hasattr(self, 'generated_code_files') or self.generated_code_files is None:
            self.generated_code_files = []
        self.generated_code_files.append(code_file)
    
    def get_all_execution_records_json(self) -> List[Dict[str, Any]]:
        """获取所有执行记录的JSON格式"""
        if not hasattr(self, 'execution_records') or self.execution_records is None:
            return []
        return [record.to_json() for record in self.execution_records]
    
    def mark_workflow_complete(self, status: ExecutionStatus):
        """标记工作流完成"""
        self.overall_status = status
        self.end_time = datetime.now().isoformat()
