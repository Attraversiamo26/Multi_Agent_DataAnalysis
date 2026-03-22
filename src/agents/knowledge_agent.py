import logging
import uuid
import json
import os
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message

from src.agents.react_agent_base import ReActAgentBase
from src.entity.states import StepState
from src.llms.llm import get_llm_by_name

logger = logging.getLogger(__name__)


class KnowledgeAgent(ReActAgentBase):

    def __init__(self, agent_name: str):
        super().__init__(
            agent_name=agent_name,
            max_iterations=15,
            react_llm="react_agent",
        )
        self.knowledge_store = KnowledgeStore()

    async def run(self, state: StepState, config: RunnableConfig):
        push_message(HumanMessage(content=f"Routing to: {self.agent_name}", id=f"record-{str(uuid.uuid4())}"))
        tools = await super().build_tools()
        # Add knowledge management tools
        from src.utils.tools import (
            add_web_link, get_link_summary, search_links, 
            categorize_link, list_links, delete_link
        )
        tools.append(add_web_link)
        tools.append(get_link_summary)
        tools.append(search_links)
        tools.append(categorize_link)
        tools.append(list_links)
        tools.append(delete_link)
        self.tools = tools
        workspace_directory = state.get("workspace_directory", "")
        current_step = state.get("current_step")
        self.workspace_directory = workspace_directory
        self.current_step = current_step
        res = await self._execute_agent_step(step_state=state, config=config)
        return {"execute_res": res}


class KnowledgeStore:
    """Knowledge store for managing web links and their summaries"""
    
    def __init__(self, storage_path: str = "knowledge_store.json"):
        self.storage_path = storage_path
        self._initialize_store()
    
    def _initialize_store(self):
        """Initialize the knowledge store if it doesn't exist"""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump({"links": []}, f, ensure_ascii=False, indent=2)
    
    def add_link(self, url: str, title: str, summary: str, categories: List[str] = None) -> Dict[str, Any]:
        """Add a new link to the knowledge store"""
        link_id = str(uuid.uuid4())
        link_data = {
            "id": link_id,
            "url": url,
            "title": title,
            "summary": summary,
            "categories": categories or [],
            "created_at": json.loads(json.dumps({"$date": "2026-03-14T00:00:00Z"}))
        }
        
        data = self._load_store()
        data["links"].append(link_data)
        self._save_store(data)
        
        return link_data
    
    def get_link(self, link_id: str) -> Dict[str, Any]:
        """Get a link by its ID"""
        data = self._load_store()
        for link in data["links"]:
            if link["id"] == link_id:
                return link
        return None
    
    def search_links(self, query: str, categories: List[str] = None) -> List[Dict[str, Any]]:
        """Search links by query and optional categories"""
        data = self._load_store()
        results = []
        
        for link in data["links"]:
            # Check if link matches categories
            if categories and not any(cat in link["categories"] for cat in categories):
                continue
            
            # Check if link matches query
            if query.lower() in link["title"].lower() or query.lower() in link["summary"].lower():
                results.append(link)
        
        return results
    
    def list_links(self, categories: List[str] = None) -> List[Dict[str, Any]]:
        """List all links, optionally filtered by categories"""
        data = self._load_store()
        if not categories:
            return data["links"]
        
        return [link for link in data["links"] if any(cat in link["categories"] for cat in categories)]
    
    def categorize_link(self, link_id: str, categories: List[str]) -> Dict[str, Any]:
        """Update the categories of a link"""
        data = self._load_store()
        for link in data["links"]:
            if link["id"] == link_id:
                link["categories"] = categories
                self._save_store(data)
                return link
        return None
    
    def delete_link(self, link_id: str) -> bool:
        """Delete a link by its ID"""
        data = self._load_store()
        original_length = len(data["links"])
        data["links"] = [link for link in data["links"] if link["id"] != link_id]
        
        if len(data["links"]) < original_length:
            self._save_store(data)
            return True
        return False
    
    def _load_store(self) -> Dict[str, Any]:
        """Load the knowledge store from disk"""
        with open(self.storage_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_store(self, data: Dict[str, Any]):
        """Save the knowledge store to disk"""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)