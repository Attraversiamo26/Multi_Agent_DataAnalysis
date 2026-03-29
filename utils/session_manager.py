from datetime import datetime
from typing import Optional, Dict, Any
import uuid
from src.entity.enhanced_models import (
    ConversationSession,
    ConversationMessage,
    MessageRole,
    ContentType,
    PlanExecutionRecord,
    StepExecutionRecord,
    StepStatus,
    PlanStatus,
    CodeExecutionRecord
)
from src.utils.storage_manager import get_storage_manager


class SessionManager:
    def __init__(self):
        self.storage = get_storage_manager()
        self.current_session_id: Optional[str] = None
    
    def create_session(self, user_id: str = "default", metadata: Optional[Dict[str, Any]] = None) -> str:
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or {}
        )
        self.storage.save_session(session)
        self.current_session_id = session_id
        return session_id
    
    def get_or_create_session(self, session_id: Optional[str] = None, user_id: str = "default") -> str:
        if session_id:
            session = self.storage.load_session(session_id)
            if session:
                self.current_session_id = session_id
                return session_id
        return self.create_session(user_id)
    
    def add_user_message(self, content: str, context_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.current_session_id:
            return False
        message = ConversationMessage(
            role=MessageRole.USER,
            content=content,
            content_type=ContentType.TEXT,
            context_id=context_id,
            metadata=metadata or {}
        )
        return self.storage.add_message(self.current_session_id, message)
    
    def add_assistant_message(self, content: str, context_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.current_session_id:
            return False
        message = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            content_type=ContentType.TEXT,
            context_id=context_id,
            metadata=metadata or {}
        )
        return self.storage.add_message(self.current_session_id, message)
    
    def add_system_message(self, content: str, context_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.current_session_id:
            return False
        message = ConversationMessage(
            role=MessageRole.SYSTEM,
            content=content,
            content_type=ContentType.TEXT,
            context_id=context_id,
            metadata=metadata or {}
        )
        return self.storage.add_message(self.current_session_id, message)
    
    def create_plan(self, plan_description: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.current_session_id:
            return None
        plan = PlanExecutionRecord(
            plan_description=plan_description,
            metadata=metadata or {}
        )
        if self.storage.add_plan(self.current_session_id, plan):
            return plan.plan_id
        return None
    
    def add_step_to_plan(self, plan_id: str, step_description: str, agent_name: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.current_session_id:
            return None
        step = StepExecutionRecord(
            step_description=step_description,
            agent_name=agent_name,
            metadata=metadata or {}
        )
        if self.storage.add_step(self.current_session_id, plan_id, step):
            return step.step_id
        return None
    
    def update_step_status(self, plan_id: str, step_id: str, status: StepStatus, result: Optional[str] = None, error: Optional[str] = None) -> bool:
        if not self.current_session_id:
            return False
        return self.storage.update_step_status(
            self.current_session_id,
            plan_id,
            step_id,
            status,
            result,
            error
        )
    
    def update_plan_status(self, plan_id: str, status: PlanStatus, error: Optional[str] = None) -> bool:
        if not self.current_session_id:
            return False
        return self.storage.update_plan_status(
            self.current_session_id,
            plan_id,
            status,
            error
        )
    
    def record_code_execution(self, plan_id: str, step_id: str, code: str, output: str = "", error: Optional[str] = None, execution_time: float = 0.0, success: bool = True) -> bool:
        if not self.current_session_id:
            return False
        code_record = CodeExecutionRecord(
            code=code,
            output=output,
            error=error,
            execution_time=execution_time,
            success=success
        )
        return self.storage.add_code_execution(
            self.current_session_id,
            plan_id,
            step_id,
            code_record
        )
    
    def get_current_session(self) -> Optional[ConversationSession]:
        if not self.current_session_id:
            return None
        return self.storage.load_session(self.current_session_id)
    
    def get_session_statistics(self) -> Dict[str, Any]:
        if not self.current_session_id:
            return {}
        return self.storage.get_session_statistics(self.current_session_id)
    
    def backup_current_session(self) -> Optional[str]:
        if not self.current_session_id:
            return None
        return self.storage.backup_session(self.current_session_id)
    
    def set_current_session(self, session_id: str) -> bool:
        session = self.storage.load_session(session_id)
        if session:
            self.current_session_id = session_id
            return True
        return False
    
    def list_all_sessions(self):
        return self.storage.list_sessions()


_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance
