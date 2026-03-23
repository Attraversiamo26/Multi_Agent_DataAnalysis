import logging
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message

from src.agents.react_agent_base import ReActAgentBase
from src.config.loader import load_yaml_config
from src.entity.states import StepState
from src.utils.python_execute import run_python_code
from src.utils.output_utils import create_search_result
from src.utils.tools import (
    list_available_data_files, read_data_file, filter_data_file
)

logger = logging.getLogger(__name__)


class SearchAgent(ReActAgentBase):
    """SearchAgent: Exclusively responsible for data retrieval operations.
    
    This agent handles:
    - Database queries
    - API calls
    - External data source access
    - File reading operations
    - Data filtering at source level
    
    It does NOT perform statistical analysis or calculations - those are 
    handled by AnalysisAgent.
    """

    def __init__(self, agent_name: str):
        # Load configuration to check if tables and data files are configured
        config = load_yaml_config("conf.yaml")
        data_sources = config.get("agents", {}).get("data_sources", {}).get("search_agent", {})
        tables_config = data_sources.get("tables", [])
        data_config = data_sources.get("data", [])
        
        # Build MCP servers dict conditionally
        mcp_servers = {
            "date": {
                "url": "http://localhost:9095/sse",
                "transport": "sse",
            }
        }
        
        # Only add table MCP service if tables are configured
        if tables_config:
            mcp_servers["table"] = {
                "url": "http://localhost:9100/sse",
                "transport": "sse",
            }
        
        # Store data configuration flag for later use in run method
        self.has_data_config = bool(data_config)
        self.agent_name = agent_name  # Store agent name for reload method
        
        super().__init__(
            agent_name=agent_name,
            mcp_servers=mcp_servers,
            max_iterations=15,
            react_llm="react_agent",
        )
    
    def reload_data_config(self):
        """Reload data configuration from conf.yaml to detect newly uploaded files."""
        try:
            config = load_yaml_config("conf.yaml")
            data_sources = config.get("agents", {}).get("data_sources", {}).get("search_agent", {})
            data_config = data_sources.get("data", [])
            self.has_data_config = bool(data_config)
            logger.info(f"Reloaded data config: {len(data_config)} files configured")
            return True
        except Exception as e:
            logger.error(f"Failed to reload data config: {e}")
            return False

    async def run(self, state: StepState, config: RunnableConfig):
        push_message(HumanMessage(content=f"Routing to: {self.agent_name}", id=f"record-{str(uuid.uuid4())}"))
        workspace_directory = state.get("workspace_directory", "")
        current_step = state.get("current_step")
        self.workspace_directory = workspace_directory
        self.current_step = current_step

        # Reload data configuration to detect newly uploaded files
        self.reload_data_config()

        try:
            tools = await super().build_tools()
        except Exception as e:
            logger.warning(f"Failed to build tools with MCP servers: {e}, falling back to basic tools")
            tools = []
        
        tools.append(run_python_code)
        
        # Add ONLY data retrieval tools (NO analysis tools)
        if self.has_data_config:
            tools.append(list_available_data_files)
            tools.append(read_data_file)
            tools.append(filter_data_file)
        
        self.tools = tools

        res = await self._execute_agent_step(step_state=state, config=config)
        # Create standardized search result
        search_result = create_search_result(
            success=True,
            query_type="data_retrieval",
            data_summary={"execution_result": res[0], "results": res[1]}
        )
        return {"execute_res": search_result}

