import logging
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message

from src.agents.react_agent_base import ReActAgentBase
from src.entity.states import StepState
from src.utils.python_execute import run_python_code
from src.utils.output_utils import create_analysis_result
from src.utils.autostat_tools import (
    autostat_get_preprocessing_suggestions,
    autostat_generate_preprocessing_code,
    autostat_get_modeling_suggestions,
    autostat_generate_modeling_code,
    autostat_format_modeling_results,
)

logger = logging.getLogger(__name__)


class AnalysisAgent(ReActAgentBase):
    """AnalysisAgent: Primary intelligent query processing agent.
    
    This agent is responsible for:
    - Statistical calculations using pandas/numpy
    - Data aggregations (sum, avg, count, group by)
    - Comparisons (WoW/YoY, growth rates, variance)
    - Derived metrics (ratios, shares, rankings, trends)
    - Data processing (cleaning, formatting, filtering, sorting)
    - Complex computations on retrieved data

    - Data preprocessing suggestions and code generation
    - Statistical modeling and machine learning
    - Model training and evaluation
    - Preprocessing → Analysis → Modeling integrated workflow
    
    It receives data from SearchAgent and performs all analytical operations
    using Python code execution with pandas, numpy, and scikit-learn libraries.
    """

    def __init__(self, agent_name: str):
        super().__init__(
            agent_name=agent_name,
            max_iterations=15,  # Increased for complex analysis
            react_llm="react_agent",
        )

    async def run(self, state: StepState, config: RunnableConfig):
        push_message(HumanMessage(content=f"Routing to: {self.agent_name}", id=f"record-{str(uuid.uuid4())}"))
        tools = await super().build_tools()
        tools.append(run_python_code)
        
        # 添加AutoSTAT增强工具
        tools.append(autostat_get_preprocessing_suggestions)
        tools.append(autostat_generate_preprocessing_code)
        tools.append(autostat_get_modeling_suggestions)
        tools.append(autostat_generate_modeling_code)
        tools.append(autostat_format_modeling_results)
        
        self.tools = tools
        workspace_directory = state.get("workspace_directory", "")
        current_step = state.get("current_step")
        self.workspace_directory = workspace_directory
        self.current_step = current_step
        res = await self._execute_agent_step(step_state=state, config=config)
        # Create standardized analysis result
        analysis_result = create_analysis_result(
            success=True,
            analysis_type="statistical_analysis",
            execution_result=str(res[0]),
            insights=["Analysis completed successfully"]
        )
        return {"execute_res": analysis_result}

