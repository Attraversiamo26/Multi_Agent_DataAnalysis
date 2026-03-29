from typing import Optional, Dict, Any, List, Callable
from src.entity.enhanced_models import (
    StepStatus,
    PlanStatus,
    PlanExecutionRecord,
    StepExecutionRecord
)
from src.utils.session_manager import get_session_manager


class ExecutionMonitor:
    def __init__(self):
        self.session_manager = get_session_manager()
        self.current_plan_id: Optional[str] = None
        self.current_step_id: Optional[str] = None
        self.step_callbacks: List[Callable] = []
        self.plan_callbacks: List[Callable] = []
    
    def register_step_callback(self, callback: Callable):
        self.step_callbacks.append(callback)
    
    def register_plan_callback(self, callback: Callable):
        self.plan_callbacks.append(callback)
    
    def start_plan(self, plan_description: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        plan_id = self.session_manager.create_plan(plan_description, metadata)
        if plan_id:
            self.current_plan_id = plan_id
            self.session_manager.update_plan_status(plan_id, PlanStatus.IN_PROGRESS)
            self._notify_plan_callbacks(plan_id, PlanStatus.IN_PROGRESS)
        return plan_id
    
    def complete_plan(self, error: Optional[str] = None):
        if self.current_plan_id:
            if error:
                status = PlanStatus.FAILED
            else:
                status = PlanStatus.COMPLETED
            self.session_manager.update_plan_status(self.current_plan_id, status, error)
            self._notify_plan_callbacks(self.current_plan_id, status, error)
            self.current_plan_id = None
    
    def fail_plan(self, error: str):
        self.complete_plan(error)
    
    def add_step(self, step_description: str, agent_name: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.current_plan_id:
            return None
        step_id = self.session_manager.add_step_to_plan(
            self.current_plan_id,
            step_description,
            agent_name,
            metadata
        )
        return step_id
    
    def start_step(self, step_id: str):
        if self.current_plan_id:
            self.current_step_id = step_id
            self.session_manager.update_step_status(
                self.current_plan_id,
                step_id,
                StepStatus.IN_PROGRESS
            )
            self._notify_step_callbacks(step_id, StepStatus.IN_PROGRESS)
    
    def complete_step(self, step_id: str, result: Optional[str] = None):
        if self.current_plan_id:
            self.session_manager.update_step_status(
                self.current_plan_id,
                step_id,
                StepStatus.COMPLETED,
                result=result
            )
            self._notify_step_callbacks(step_id, StepStatus.COMPLETED, result=result)
            if self.current_step_id == step_id:
                self.current_step_id = None
    
    def fail_step(self, step_id: str, error: str, retry_allowed: bool = True):
        if self.current_plan_id:
            step = self._get_step(step_id)
            if step and retry_allowed and step.retry_count < step.max_retries:
                step.retry_count += 1
                self.session_manager.update_step_status(
                    self.current_plan_id,
                    step_id,
                    StepStatus.PENDING,
                    error=error
                )
                self._notify_step_callbacks(step_id, StepStatus.PENDING, error=error)
            else:
                self.session_manager.update_step_status(
                    self.current_plan_id,
                    step_id,
                    StepStatus.FAILED,
                    error=error
                )
                self._notify_step_callbacks(step_id, StepStatus.FAILED, error=error)
            if self.current_step_id == step_id:
                self.current_step_id = None
    
    def _get_step(self, step_id: str) -> Optional[StepExecutionRecord]:
        if not self.current_plan_id:
            return None
        session = self.session_manager.get_current_session()
        if not session:
            return None
        for plan in session.plans:
            if plan.plan_id == self.current_plan_id:
                for step in plan.steps:
                    if step.step_id == step_id:
                        return step
        return None
    
    def _get_plan(self) -> Optional[PlanExecutionRecord]:
        if not self.current_plan_id:
            return None
        session = self.session_manager.get_current_session()
        if not session:
            return None
        for plan in session.plans:
            if plan.plan_id == self.current_plan_id:
                return plan
        return None
    
    def _notify_step_callbacks(self, step_id: str, status: StepStatus, result: Optional[str] = None, error: Optional[str] = None):
        for callback in self.step_callbacks:
            try:
                callback(step_id, status, result, error)
            except Exception:
                pass
    
    def _notify_plan_callbacks(self, plan_id: str, status: PlanStatus, error: Optional[str] = None):
        for callback in self.plan_callbacks:
            try:
                callback(plan_id, status, error)
            except Exception:
                pass
    
    def get_current_plan_status(self) -> Optional[Dict[str, Any]]:
        plan = self._get_plan()
        if plan:
            return {
                "plan_id": plan.plan_id,
                "status": plan.status,
                "started_at": plan.started_at,
                "completed_at": plan.completed_at,
                "step_summary": plan.get_step_summary()
            }
        return None
    
    def get_current_step_status(self) -> Optional[Dict[str, Any]]:
        if not self.current_step_id:
            return None
        step = self._get_step(self.current_step_id)
        if step:
            return {
                "step_id": step.step_id,
                "status": step.status,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
                "retry_count": step.retry_count
            }
        return None


_execution_monitor_instance: Optional[ExecutionMonitor] = None


def get_execution_monitor() -> ExecutionMonitor:
    global _execution_monitor_instance
    if _execution_monitor_instance is None:
        _execution_monitor_instance = ExecutionMonitor()
    return _execution_monitor_instance
