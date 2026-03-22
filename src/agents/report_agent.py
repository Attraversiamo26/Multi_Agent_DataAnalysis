import json
import logging
import uuid
import os
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message
from langgraph.types import Command

from src.entity.states import PlanState
from src.llms.llm import get_llm_by_name
from src.prompts.template import get_prompt_without_render
from src.utils.llm_utils import astream
from src.utils.output_utils import create_report_result
from src.utils.report_intent_recognizer import ReportIntentRecognizer, ReportIntentResult

logger = logging.getLogger(__name__)
import platform

system = platform.system()


class ReportAgent:
    """ReportAgent: Synthesize comprehensive, structured reports.
    
    This agent is responsible for:
    - Synthesizing user conversation history
    - Integrating analytical results from AnalysisAgent
    - Incorporating visualizations from VisualizationAgent
    - Producing comprehensive, structured reports with:
      - Proper formatting and organization
      - Executive summaries
      - Key findings and insights
      - Data-driven recommendations (when appropriate)
      - Clear conclusions
    - **AutoSTAT增强功能**:
      - Professional Markdown report generation with structured sections
      - Modeling results formatting and presentation
      - AutoSTAT-style comprehensive analysis reports
    
    It receives the complete execution context and creates the final
    deliverable for the user.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.intent_recognizer = ReportIntentRecognizer()

    def _extract_last_assistant_message(self, messages):
        """Extract the most recent assistant message content."""
        for msg in reversed(messages or []):
            if isinstance(msg, dict) and msg.get("content"):
                return msg.get("content")
        return ""

    def _format_execution_results(self, executed_steps):
        """Format executed steps into JSON strings."""
        results = []
        charts = []
        for step in executed_steps:
            results.append(json.dumps({
                "title": step.title,
                "description": step.description,
                "execution_result": step.summary_execution_res
            }, indent=2, ensure_ascii=False))
            if 'chart_path' in step.summary_execution_res:
                charts.append(step.summary_execution_res['chart_path'])
        return results, charts

    def _detect_charts(self, execution_results: List[str]) -> List[str]:
        """Detect chart paths from execution results."""
        charts = []
        for result in execution_results:
            try:
                data = json.loads(result)
                if isinstance(data, dict) and 'chart_path' in data:
                    charts.append(data['chart_path'])
                elif isinstance(data, dict) and 'execution_result' in data:
                    exec_result = data['execution_result']
                    if isinstance(exec_result, dict) and 'chart_path' in exec_result:
                        charts.append(exec_result['chart_path'])
                    elif isinstance(exec_result, str):
                        try:
                            exec_data = json.loads(exec_result)
                            if isinstance(exec_data, dict) and 'chart_path' in exec_data:
                                charts.append(exec_data['chart_path'])
                        except:
                            pass
            except:
                pass
        return charts

    def _generate_report_template(self, detail_level: str = "standard", data_only: bool = False) -> str:
        """Generate report template based on detail level.
        
        Args:
            detail_level: Level of report detail (brief, standard, detailed, adaptive)
            data_only: If True, use data-only templates without analysis/recommendations/conclusions
        
        Returns:
            Rendered template string with configuration parameters
        """
        if data_only:
            return get_prompt_without_render("data_only_standard")
        
        base_template = get_prompt_without_render("report_adaptive")
        
        config_params = f"""
## Configuration Parameters
- **detail_level**: {detail_level}
- **include_analysis**: true
- **adaptive_mode**: true
"""
        return base_template.replace("## Configuration Parameters", config_params)

    def _export_report(self, content: str, export_format: str = "txt") -> str:
        """Export report to specified format."""
        reports_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.{export_format}"
        filepath = os.path.join(reports_dir, filename)
        
        if export_format == "txt":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        elif export_format == "json":
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"report": content}, f, ensure_ascii=False, indent=2)
        
        return filepath

    def _should_generate_report(self, user_question: str, executed_steps: list, all_charts: list) -> ReportIntentResult:
        """Determine if user wants a full analysis report or just data results.
        
        Args:
            user_question: Original user question
            executed_steps: List of executed steps
            all_charts: List of chart paths
        
        Returns:
            ReportIntentResult with detailed decision information
        """
        try:
            logger.info(f"Starting report intent recognition for question: {user_question}")
            logger.info(f"Execution context: {len(executed_steps)} steps, {len(all_charts)} charts")
            
            result = self.intent_recognizer.recognize(
                user_question=user_question,
                executed_steps=len(executed_steps) if executed_steps else None,
                chart_count=len(all_charts) if all_charts else None
            )
            
            logger.info(f"Report intent decision - Should generate report: {result.should_generate_report}")
            logger.info(f"Confidence score: {result.confidence_score:.2f}")
            logger.info(f"Decision reason: {result.decision_reason}")
            
            if result.matched_keywords:
                logger.info(f"Matched keywords: {[kw.keyword for kw in result.matched_keywords]}")
            
            logger.info(f"Complexity indicators: {result.complexity_indicators}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in report intent recognition: {str(e)}", exc_info=True)
            logger.warning("Falling back to default behavior: generate report")
            return ReportIntentResult(
                should_generate_report=True,
                matched_keywords=[],
                confidence_score=0.5,
                decision_reason=f"Fallback due to error: {str(e)}",
                complexity_indicators={}
            )

    async def run(self, state: PlanState, config: RunnableConfig):
        logger.info("=" * 80)
        logger.info("ReportAgent execution started")
        logger.info("=" * 80)
        
        try:
            push_message(HumanMessage(
                content="Generating final analysis report",
                id=f"record-{uuid.uuid4()}"
            ))

            messages = state.get("history", [])
            executed_steps = state.get('executed_steps', [])
            user_question = state.get('user_question', '')

            logger.info(f"User question: {user_question}")
            logger.info(f"Number of executed steps: {len(executed_steps)}")

            last_assistant_content = self._extract_last_assistant_message(messages)

            exec_results, detected_charts = self._format_execution_results(executed_steps)
            exec_results.append(last_assistant_content)
            
            additional_charts = self._detect_charts(exec_results)
            all_charts = list(set(detected_charts + additional_charts))

            logger.info(f"Number of charts generated: {len(all_charts)}")

            detail_level = "standard"
            if len(all_charts) > 3:
                detail_level = "detailed"
            elif len(executed_steps) < 3:
                detail_level = "brief"
            
            logger.info(f"Detail level determined: {detail_level}")

            intent_result = self._should_generate_report(user_question, executed_steps, all_charts)
            should_generate_full_report = intent_result.should_generate_report
            
            if should_generate_full_report:
                push_message(HumanMessage(
                    content=f"Generating comprehensive analysis report (confidence: {intent_result.confidence_score:.2f})",
                    id=f"record-{uuid.uuid4()}"
                ))
            else:
                push_message(HumanMessage(
                    content=f"Generating data-only response (confidence: {intent_result.confidence_score:.2f})",
                    id=f"record-{uuid.uuid4()}"
                ))

            system_prompt = self._generate_report_template(detail_level, data_only=not should_generate_full_report)

            charts_section = """
## Charts Generated
"""
            if all_charts:
                charts_section += "\n".join([f"- {chart}" for chart in all_charts])
            else:
                charts_section += "No charts generated"

            if should_generate_full_report:
                user_prompt = f"""
## Original User Question
{user_question}

## Execution Results
{"\n".join(exec_results)}

{charts_section}

Please generate a comprehensive analysis report based on the execution results.

Remember, only generate it based on the execution result data I provided. Never fabricate, simulate, or calculate data yourself. Especially for multiples, ratios, percentages - if these are not in the result data, don't calculate them yourself.
"""
            else:
                user_prompt = f"""
## Original User Question
{user_question}

## Execution Results
{"\n".join(exec_results)}

{charts_section}

Please provide a concise data-focused response that:
1. Directly answers the user's question with the data results
2. Presents key statistics and numbers clearly
3. References charts if available
4. Does NOT include detailed analysis, recommendations, or conclusions
5. Keeps the response factual and data-driven

Remember, only present the data from the execution results. Never fabricate, simulate, or calculate data yourself.
"""

            user_msg = {"role": "user", "content": user_prompt}
            messages.append(user_msg)

            report_messages = [
                {"role": "system", "content": system_prompt},
                user_msg
            ]

            logger.info(f"Report generation mode: {'full report' if should_generate_full_report else 'data-only'}")
            logger.info(f"Using template: {'report_adaptive' if should_generate_full_report else 'data_only_standard'}")

            llm = get_llm_by_name(self.agent_name)
            result = await astream(llm, report_messages, {"thinking": {"type": "enabled"}}, config)
            response_content = result.content

            export_path = self._export_report(response_content)
            logger.info(f"Report exported to: {export_path}")

            final_content = f"{response_content}\n\n---\nReport exported to: {export_path}"

            # Create standardized report result
            report_result = create_report_result(
                success=True,
                report_format="txt",
                report_path=export_path,
                report_content=response_content,
                word_count=len(response_content.split())
            )

            messages.append({"role": "assistant", "content": final_content})
            logger.info(f"ReportAgent execution completed successfully")
            logger.info("=" * 80)

            return Command(
                update={"report_export_path": export_path, "report_result": report_result},
                goto="__end__",
            )
            
        except Exception as e:
            logger.error(f"Error in ReportAgent execution: {str(e)}", exc_info=True)
            logger.warning("Falling back to simple data response")
            
            try:
                fallback_content = "An error occurred during report generation. Here are the raw execution results:\n\n"
                if executed_steps:
                    for step in executed_steps:
                        fallback_content += f"## {step.title}\n{step.description}\n{step.summary_execution_res}\n\n"
                
                export_path = self._export_report(fallback_content)
                final_content = f"{fallback_content}\n\n---\nReport exported to: {export_path}"
                
                # Create standardized report result for fallback
                report_result = create_report_result(
                    success=False,
                    report_format="txt",
                    report_path=export_path,
                    report_content=fallback_content,
                    word_count=len(fallback_content.split()),
                    error_message=str(e)
                )
                
                logger.info("Fallback response generated successfully")
                logger.info("=" * 80)
                
                return Command(
                    update={"report_export_path": export_path, "report_result": report_result},
                    goto="__end__",
                )
            except Exception as fallback_error:
                logger.critical(f"Even fallback failed: {str(fallback_error)}", exc_info=True)
                logger.info("=" * 80)
                return Command(
                    update={"report_export_path": None},
                    goto="__end__",
                )
