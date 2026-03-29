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
        # 只输出摘要信息，不输出完整数据集或列名
        def summarize_result(data):
            if data is None:
                return None
            if isinstance(data, str):
                return data
            if isinstance(data, (int, float, bool)):
                return data
            
            # 处理 dataclass 对象（如 AnalysisResult、SearchResult 等）
            if hasattr(data, '__dataclass_fields__'):
                try:
                    # 尝试将 dataclass 转换为字典
                    result_dict = {}
                    for field_name in data.__dataclass_fields__:
                        try:
                            value = getattr(data, field_name)
                            result_dict[field_name] = summarize_result(value)
                        except Exception:
                            pass
                    return result_dict
                except Exception:
                    # 如果转换失败，返回字符串表示
                    return str(data)
            
            if isinstance(data, list):
                if len(data) == 0:
                    return []
                # 递归处理列表中的每个元素
                processed_items = [summarize_result(item) for item in data]
                if len(processed_items) > 5:
                    return f"[List with {len(processed_items)} items - showing first 5]: {processed_items[:5]}"
                return processed_items
            
            if isinstance(data, dict):
                # 过滤掉完整数据集相关的字段
                summarized = {}
                for key, value in data.items():
                    # 跳过完整数据、列名等
                    if any(keyword in str(key).lower() for keyword in ['data', 'columns', 'values', 'records']):
                        if isinstance(value, (list, dict)) and len(str(value)) > 500:
                            summarized[key] = f"[Summary] {type(value).__name__} with {len(value) if hasattr(value, '__len__') else 'multiple'} items"
                        else:
                            summarized[key] = summarize_result(value)
                    else:
                        summarized[key] = summarize_result(value)
                return summarized
            
            # 其他类型转换为字符串但截断过长的内容
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
    
    # 意图识别 
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
