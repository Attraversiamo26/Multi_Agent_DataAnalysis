import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.entity.enhanced_models import (
    ConversationMessage,
    StepExecutionRecord,
    PlanExecutionRecord,
    CodeExecutionRecord,
    ConversationSession,
    StepStatus,
    PlanStatus
)


class StorageManager:
    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.backups_dir = self.base_dir / "backups"
        self.archives_dir = self.base_dir / "archives"
        
        for dir_path in [self.sessions_dir, self.backups_dir, self.archives_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _get_session_file(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"
    
    def _get_backup_file(self, session_id: str, timestamp: str) -> Path:
        return self.backups_dir / f"{session_id}_backup_{timestamp}.json"
    
    def _get_archive_file(self, session_id: str, archive_date: str) -> Path:
        return self.archives_dir / f"{session_id}_archive_{archive_date}.json"
    
    def save_session(self, session: ConversationSession) -> str:
        session_file = self._get_session_file(session.session_id)
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session.model_dump(), f, ensure_ascii=False, indent=2, default=str)
        return session.session_id
    
    def load_session(self, session_id: str) -> Optional[ConversationSession]:
        session_file = self._get_session_file(session_id)
        if not session_file.exists():
            return None
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ConversationSession(**data)
        except Exception:
            return None
    
    def list_sessions(self) -> List[str]:
        session_files = self.sessions_dir.glob("*.json")
        return [f.stem for f in session_files]
    
    def delete_session(self, session_id: str) -> bool:
        session_file = self._get_session_file(session_id)
        if session_file.exists():
            session_file.unlink()
            return True
        return False
    
    def add_message(self, session_id: str, message: ConversationMessage) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        session.add_message(message)
        self.save_session(session)
        return True
    
    def add_plan(self, session_id: str, plan: PlanExecutionRecord) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        session.add_plan(plan)
        self.save_session(session)
        return True
    
    def update_plan_status(self, session_id: str, plan_id: str, status: PlanStatus, error: Optional[str] = None) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        for plan in session.plans:
            if plan.plan_id == plan_id:
                if status == PlanStatus.IN_PROGRESS:
                    plan.mark_in_progress()
                elif status == PlanStatus.COMPLETED or status == PlanStatus.FAILED:
                    plan.update_status_based_on_steps()
                session.last_active_time = datetime.now()
                self.save_session(session)
                return True
        return False
    
    def add_step(self, session_id: str, plan_id: str, step: StepExecutionRecord) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        for plan in session.plans:
            if plan.plan_id == plan_id:
                plan.add_step(step)
                session.last_active_time = datetime.now()
                self.save_session(session)
                return True
        return False
    
    def update_step_status(self, session_id: str, plan_id: str, step_id: str, status: StepStatus, result: Optional[str] = None, error: Optional[str] = None) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        for plan in session.plans:
            if plan.plan_id == plan_id:
                for step in plan.steps:
                    if step.step_id == step_id:
                        if status == StepStatus.IN_PROGRESS:
                            step.mark_in_progress()
                        elif status == StepStatus.COMPLETED:
                            step.mark_completed(result=result or "")
                        elif status == StepStatus.FAILED:
                            step.mark_failed(error=error or "")
                        plan.update_status_based_on_steps()
                        session.last_active_time = datetime.now()
                        self.save_session(session)
                        return True
        return False
    
    def add_code_execution(self, session_id: str, plan_id: str, step_id: str, code_record: CodeExecutionRecord) -> bool:
        session = self.load_session(session_id)
        if not session:
            return False
        session.last_active_time = datetime.now()
        self.save_session(session)
        return True
    
    def backup_session(self, session_id: str) -> Optional[str]:
        session_file = self._get_session_file(session_id)
        if not session_file.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self._get_backup_file(session_id, timestamp)
        import shutil
        shutil.copy2(session_file, backup_file)
        return str(backup_file)
    
    def archive_old_sessions(self, days_old: int = 30) -> int:
        archive_date = datetime.now().strftime("%Y%m")
        cutoff = datetime.now().timestamp() - (days_old * 86400)
        archived_count = 0
        for session_file in self.sessions_dir.glob("*.json"):
            if session_file.stat().st_mtime < cutoff:
                session_id = session_file.stem
                archive_file = self._get_archive_file(session_id, archive_date)
                import shutil
                shutil.move(str(session_file), str(archive_file))
                archived_count += 1
        return archived_count
    
    def query_messages_by_time_range(self, session_id: str, start_time: datetime, end_time: datetime) -> List[ConversationMessage]:
        session = self.load_session(session_id)
        if not session:
            return []
        return session.get_messages_in_time_range(start_time, end_time)
    
    def query_messages_by_keyword(self, session_id: str, keyword: str) -> List[ConversationMessage]:
        session = self.load_session(session_id)
        if not session:
            return []
        return session.search_messages(keyword)
    
    def query_plans_by_status(self, session_id: str, status: PlanStatus) -> List[PlanExecutionRecord]:
        session = self.load_session(session_id)
        if not session:
            return []
        return [plan for plan in session.plans if plan.status == status]
    
    def query_steps_by_status(self, session_id: str, plan_id: str, status: StepStatus) -> List[StepExecutionRecord]:
        session = self.load_session(session_id)
        if not session:
            return []
        for plan in session.plans:
            if plan.plan_id == plan_id:
                return [step for step in plan.steps if step.status == status]
        return []
    
    def get_session_statistics(self, session_id: str) -> Dict[str, Any]:
        session = self.load_session(session_id)
        if not session:
            return {}
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "created_time": session.created_time,
            "last_active_time": session.last_active_time,
            "message_count": len(session.messages),
            "plan_count": len(session.plans),
            "is_active": session.is_active
        }
    
    def get_all_sessions_statistics(self) -> List[Dict[str, Any]]:
        stats = []
        for session_id in self.list_sessions():
            session_stats = self.get_session_statistics(session_id)
            if session_stats:
                stats.append(session_stats)
        return stats


_storage_manager_instance: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    global _storage_manager_instance
    if _storage_manager_instance is None:
        _storage_manager_instance = StorageManager()
    return _storage_manager_instance
