"""
Enhanced Data Models for Data Agent System
包含对话历史记录、计划执行跟踪、执行结果记录等完整数据模型
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4, UUID

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """对话消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    THINKING = "thinking"


class ContentType(str, Enum):
    """内容类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    CHART = "chart"
    TABLE = "table"
    CODE = "code"


class StepStatus(str, Enum):
    """步骤执行状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class PlanStatus(str, Enum):
    """计划执行状态枚举"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConversationMessage(BaseModel):
    """对话消息记录模型"""
    message_id: str = Field(default_factory=lambda: str(uuid4()), description="消息唯一标识符")
    session_id: str = Field(..., description="会话ID")
    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    content_type: ContentType = Field(default=ContentType.TEXT, description="内容类型")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息时间戳")
    context_id: Optional[str] = Field(default=None, description="关联上下文ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "session_20240101_120000",
                "role": "user",
                "content": "有多少个收寄省？",
                "content_type": "text",
                "timestamp": "2024-01-01T12:00:00Z",
                "context_id": "plan_550e8400-e29b-41d4-a716-446655440001",
                "metadata": {}
            }
        }


class StepExecutionRecord(BaseModel):
    """步骤执行记录模型"""
    step_id: str = Field(default_factory=lambda: str(uuid4()), description="步骤唯一标识符")
    plan_id: str = Field(..., description="所属计划ID")
    session_id: str = Field(..., description="会话ID")
    step_index: int = Field(..., description="步骤在计划中的索引")
    title: str = Field(..., description="步骤标题")
    description: str = Field(..., description="步骤描述")
    agent: str = Field(..., description="执行该步骤的agent名称")
    status: StepStatus = Field(default=StepStatus.PENDING, description="执行状态")
    start_time: Optional[datetime] = Field(default=None, description="开始执行时间")
    end_time: Optional[datetime] = Field(default=None, description="执行结束时间")
    duration_seconds: Optional[float] = Field(default=None, description="执行耗时（秒）")
    output_result: Optional[str] = Field(default=None, description="执行输出结果")
    summary_result: Optional[str] = Field(default=None, description="执行结果摘要")
    error_message: Optional[str] = Field(default=None, description="错误信息（如有）")
    error_stacktrace: Optional[str] = Field(default=None, description="错误堆栈（如有）")
    retry_count: int = Field(default=0, description="重试次数")
    max_retries: int = Field(default=3, description="最大重试次数")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具列表")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    def calculate_duration(self) -> Optional[float]:
        """计算执行耗时"""
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            self.duration_seconds = duration
            return duration
        return None

    def mark_in_progress(self) -> None:
        """标记步骤开始执行"""
        self.status = StepStatus.IN_PROGRESS
        self.start_time = datetime.now()

    def mark_completed(self, result: Optional[str] = None, summary: Optional[str] = None) -> None:
        """标记步骤执行完成"""
        self.status = StepStatus.COMPLETED
        self.end_time = datetime.now()
        self.output_result = result
        self.summary_result = summary or result
        self.calculate_duration()

    def mark_failed(self, error: Optional[str] = None, stacktrace: Optional[str] = None) -> None:
        """标记步骤执行失败"""
        self.status = StepStatus.FAILED
        self.end_time = datetime.now()
        self.error_message = error
        self.error_stacktrace = stacktrace
        self.calculate_duration()

    def can_retry(self) -> bool:
        """判断是否可以重试"""
        return self.retry_count < self.max_retries and self.status == StepStatus.FAILED

    def mark_retrying(self) -> None:
        """标记正在重试"""
        self.status = StepStatus.RETRYING
        self.retry_count += 1
        self.start_time = datetime.now()
        self.end_time = None
        self.error_message = None
        self.error_stacktrace = None

    class Config:
        json_schema_extra = {
            "example": {
                "step_id": "550e8400-e29b-41d4-a716-446655440000",
                "plan_id": "plan_550e8400-e29b-41d4-a716-446655440001",
                "session_id": "session_20240101_120000",
                "step_index": 0,
                "title": "读取收寄省字段",
                "description": "从文件中读取收寄省列",
                "agent": "search_agent",
                "status": "completed",
                "start_time": "2024-01-01T12:00:00Z",
                "end_time": "2024-01-01T12:00:05Z",
                "duration_seconds": 5.2,
                "output_result": "读取到150条记录...",
                "summary_result": "成功读取数据",
                "tools_used": ["read_data_file"],
                "metadata": {}
            }
        }


class PlanExecutionRecord(BaseModel):
    """计划执行记录模型"""
    plan_id: str = Field(default_factory=lambda: str(uuid4()), description="计划唯一标识符")
    session_id: str = Field(..., description="会话ID")
    original_question: str = Field(..., description="原始用户问题")
    locale: str = Field(..., description="语言环境")
    thought: str = Field(..., description="计划思考过程")
    title: str = Field(..., description="计划标题")
    status: PlanStatus = Field(default=PlanStatus.CREATED, description="计划状态")
    created_time: datetime = Field(default_factory=datetime.now, description="计划创建时间")
    start_time: Optional[datetime] = Field(default=None, description="开始执行时间")
    end_time: Optional[datetime] = Field(default=None, description="执行结束时间")
    total_duration_seconds: Optional[float] = Field(default=None, description="总执行耗时")
    steps: List[StepExecutionRecord] = Field(default_factory=list, description="步骤执行记录列表")
    questions: List[str] = Field(default_factory=list, description="需要用户确认的问题")
    retrieved_info: Optional[str] = Field(default=None, description="检索到的上下文信息")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    def add_step(self, step: StepExecutionRecord) -> None:
        """添加步骤记录"""
        self.steps.append(step)

    def get_step_by_id(self, step_id: str) -> Optional[StepExecutionRecord]:
        """根据步骤ID获取步骤记录"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_step_by_index(self, index: int) -> Optional[StepExecutionRecord]:
        """根据索引获取步骤记录"""
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def mark_in_progress(self) -> None:
        """标记计划开始执行"""
        self.status = PlanStatus.IN_PROGRESS
        self.start_time = datetime.now()

    def update_status_based_on_steps(self) -> None:
        """根据步骤状态更新计划状态"""
        if not self.steps:
            self.status = PlanStatus.CREATED
            return

        completed_count = sum(1 for step in self.steps if step.status == StepStatus.COMPLETED)
        failed_count = sum(1 for step in self.steps if step.status == StepStatus.FAILED)
        in_progress_count = sum(1 for step in self.steps if step.status == StepStatus.IN_PROGRESS)

        if failed_count > 0:
            self.status = PlanStatus.FAILED
        elif completed_count == len(self.steps):
            self.status = PlanStatus.COMPLETED
            self.end_time = datetime.now()
            if self.start_time:
                self.total_duration_seconds = (self.end_time - self.start_time).total_seconds()
        elif completed_count > 0:
            self.status = PlanStatus.PARTIALLY_COMPLETED
        elif in_progress_count > 0:
            self.status = PlanStatus.IN_PROGRESS

    def get_completed_steps(self) -> List[StepExecutionRecord]:
        """获取已完成的步骤"""
        return [step for step in self.steps if step.status == StepStatus.COMPLETED]

    def get_failed_steps(self) -> List[StepExecutionRecord]:
        """获取失败的步骤"""
        return [step for step in self.steps if step.status == StepStatus.FAILED]

    def get_total_duration(self) -> Optional[float]:
        """获取总执行耗时"""
        if self.total_duration_seconds is not None:
            return self.total_duration_seconds
        return sum(step.duration_seconds for step in self.steps if step.duration_seconds is not None)

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "plan_550e8400-e29b-41d4-a716-446655440001",
                "session_id": "session_20240101_120000",
                "original_question": "有多少个收寄省？",
                "locale": "zh-CN",
                "thought": "用户问题要求统计...",
                "title": "统计收寄省数量",
                "status": "completed",
                "created_time": "2024-01-01T12:00:00Z",
                "start_time": "2024-01-01T12:00:00Z",
                "end_time": "2024-01-01T12:00:10Z",
                "total_duration_seconds": 10.5,
                "steps": [],
                "questions": [],
                "retrieved_info": "检索到的数据信息...",
                "metadata": {}
            }
        }


class CodeExecutionRecord(BaseModel):
    """Python代码执行记录模型"""
    execution_id: str = Field(default_factory=lambda: str(uuid4()), description="执行唯一标识符")
    session_id: str = Field(..., description="会话ID")
    step_id: Optional[str] = Field(default=None, description="关联的步骤ID")
    plan_id: Optional[str] = Field(default=None, description="关联的计划ID")
    code: str = Field(..., description="执行的Python代码")
    start_time: datetime = Field(default_factory=datetime.now, description="开始执行时间")
    end_time: Optional[datetime] = Field(default=None, description="执行结束时间")
    duration_seconds: Optional[float] = Field(default=None, description="执行耗时")
    stdout: Optional[str] = Field(default=None, description="标准输出")
    stderr: Optional[str] = Field(default=None, description="标准错误")
    success: bool = Field(default=False, description="是否执行成功")
    result_data: Optional[Dict[str, Any]] = Field(default=None, description="结果数据")
    exception_type: Optional[str] = Field(default=None, description="异常类型")
    exception_message: Optional[str] = Field(default=None, description="异常信息")
    exception_traceback: Optional[str] = Field(default=None, description="异常堆栈")
    resource_usage: Optional[Dict[str, Any]] = Field(default=None, description="资源使用情况")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    def mark_completed(self, stdout: str, result_data: Optional[Dict[str, Any]] = None) -> None:
        """标记代码执行完成"""
        self.end_time = datetime.now()
        self.stdout = stdout
        self.success = True
        self.result_data = result_data
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def mark_failed(self, stderr: str, exception_type: Optional[str] = None, 
                    exception_message: Optional[str] = None, 
                    exception_traceback: Optional[str] = None) -> None:
        """标记代码执行失败"""
        self.end_time = datetime.now()
        self.stderr = stderr
        self.success = False
        self.exception_type = exception_type
        self.exception_message = exception_message
        self.exception_traceback = exception_traceback
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec_550e8400-e29b-41d4-a716-446655440000",
                "session_id": "session_20240101_120000",
                "step_id": "step_550e8400-e29b-41d4-a716-446655440001",
                "plan_id": "plan_550e8400-e29b-41d4-a716-446655440002",
                "code": "import pandas as pd\nprint('Hello World')",
                "start_time": "2024-01-01T12:00:00Z",
                "end_time": "2024-01-01T12:00:01Z",
                "duration_seconds": 1.2,
                "stdout": "Hello World",
                "success": True,
                "metadata": {}
            }
        }


class ConversationSession(BaseModel):
    """会话记录模型"""
    session_id: str = Field(..., description="会话唯一标识符")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    created_time: datetime = Field(default_factory=datetime.now, description="会话创建时间")
    last_active_time: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    messages: List[ConversationMessage] = Field(default_factory=list, description="对话消息列表")
    plans: List[PlanExecutionRecord] = Field(default_factory=list, description="计划执行记录列表")
    is_active: bool = Field(default=True, description="会话是否活跃")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    def add_message(self, message: ConversationMessage) -> None:
        """添加对话消息"""
        self.messages.append(message)
        self.last_active_time = datetime.now()

    def add_plan(self, plan: PlanExecutionRecord) -> None:
        """添加计划执行记录"""
        self.plans.append(plan)
        self.last_active_time = datetime.now()

    def get_latest_plan(self) -> Optional[PlanExecutionRecord]:
        """获取最新的计划执行记录"""
        if self.plans:
            return self.plans[-1]
        return None

    def get_messages_by_role(self, role: MessageRole) -> List[ConversationMessage]:
        """根据角色获取消息"""
        return [msg for msg in self.messages if msg.role == role]

    def search_messages(self, keyword: str) -> List[ConversationMessage]:
        """搜索包含关键词的消息"""
        keyword_lower = keyword.lower()
        return [msg for msg in self.messages if keyword_lower in msg.content.lower()]

    def get_messages_in_time_range(self, start_time: datetime, end_time: datetime) -> List[ConversationMessage]:
        """获取时间范围内的消息"""
        return [msg for msg in self.messages if start_time <= msg.timestamp <= end_time]

    def mark_inactive(self) -> None:
        """将会话标记为不活跃"""
        self.is_active = False
        self.last_active_time = datetime.now()

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_20240101_120000",
                "user_id": "user_123",
                "created_time": "2024-01-01T12:00:00Z",
                "last_active_time": "2024-01-01T12:00:10Z",
                "messages": [],
                "plans": [],
                "is_active": True,
                "metadata": {}
            }
        }
