import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message

from src.agents.react_agent_base import ReActAgentBase
from src.config.loader import load_yaml_config
from src.entity.states import StepState
from src.utils.python_execute import run_python_code
from src.utils.output_utils import create_visualization_result
from src.utils.autostat_tools import (
    autostat_suggest_charts,
    autostat_generate_visualization_code,
)

logger = logging.getLogger(__name__)


class VisualizationAgent(ReActAgentBase):
    """VisualizationAgent: Generate publication-quality data visualizations.
    
    This agent is responsible for:
    - Selecting appropriate chart types based on data and query requirements
    - Creating clear, informative visualizations using matplotlib, seaborn, or plotly
    - Generating publication-quality charts with proper formatting
    - Supporting multiple chart types: bar, line, pie, scatter, heatmap, boxplot, etc.
    - Adding appropriate titles, labels, legends, and annotations
    - **AutoSTAT增强功能**:
      - Professional visualization suggestions based on data characteristics
      - AutoSTAT-style Plotly interactive chart generation
      - Insight-driven chart recommendations
    
    It receives analyzed data from AnalysisAgent and creates visual representations
    that enhance understanding of the insights.
    """

    def __init__(self, agent_name: str):
        # Load configuration
        config = load_yaml_config("conf.yaml")
        
        # Build MCP servers dict
        mcp_servers = {
            "date": {
                "url": "http://localhost:9095/sse",
                "transport": "sse",
            }
        }
        
        super().__init__(
            agent_name=agent_name,
            mcp_servers=mcp_servers,
            max_iterations=15,
            react_llm="react_agent",
        )

    async def run(self, state: StepState, config: RunnableConfig):
        workspace_directory = state.get("workspace_directory", "")
        current_step = state.get("current_step")
        self.workspace_directory = workspace_directory
        self.current_step = current_step

        tools = await super().build_tools()
        tools.append(run_python_code)
        
        # Add visualization tools - comprehensive chart generation capabilities
        from src.utils.tools import (
            generate_bar_chart, 
            generate_line_chart, 
            generate_pie_chart, 
            generate_scatter_plot
        )
        tools.append(generate_bar_chart)
        tools.append(generate_line_chart)
        tools.append(generate_pie_chart)
        tools.append(generate_scatter_plot)
        
        # 添加AutoSTAT增强工具
        tools.append(autostat_suggest_charts)
        tools.append(autostat_generate_visualization_code)
        
        self.tools = tools

        res = await self._execute_agent_step(step_state=state, config=config)
        
        # 处理返回结果：_execute_agent_step 返回 (action_res, results)
        # 如果 action_res 是 {"terminate": ...}，我们应该使用 results
        action_res, results = res
        if isinstance(action_res, dict) and "terminate" in action_res:
            # 有 terminate 标记，使用实际 results
            final_results = results
        else:
            final_results = [action_res] if action_res else results
        
        # Create standardized visualization result
        visualization_result = create_visualization_result(
            success=True,
            chart_type="interactive",
            chart_title="Data Visualization",
            chart_description="Visualization created successfully",
            variables_used=["data_variables"]
        )
        return {"execute_res": visualization_result}