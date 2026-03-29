import json
import logging
import uuid
import os
from typing import List, Dict, Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message

from src.agents.react_agent_base import ReActAgentBase
from src.entity.states import StepState

logger = logging.getLogger(__name__)


class ManageAgent(ReActAgentBase):

    def __init__(self, agent_name: str):
        super().__init__(
            agent_name=agent_name,
            max_iterations=10,
            react_llm="react_agent",
        )

    async def run(self, state: StepState, config: RunnableConfig):
        tools = await super().build_tools()
        # Add document management tools
        from src.utils.tools import (
            list_documents, upload_document, delete_document, preview_document
        )
        tools.append(list_documents)
        tools.append(upload_document)
        tools.append(delete_document)
        tools.append(preview_document)
        self.tools = tools
        workspace_directory = state.get("workspace_directory", "")
        current_step = state.get("current_step")
        self.workspace_directory = workspace_directory
        self.current_step = current_step
        res = await self._execute_agent_step(step_state=state, config=config)
        
        # 处理返回结果：_execute_agent_step 返回 (action_res, results)
        # 如果 action_res 是 {"terminate": ...}，我们应该使用 results
        action_res, results = res
        if isinstance(action_res, dict) and "terminate" in action_res:
            # 有 terminate 标记，使用实际 results
            final_results = results
        else:
            final_results = [action_res] if action_res else results
        
        return {"execute_res": final_results}
