"""
Unified Output Utilities - 统一输出工具
Standardized output formats for all agents
所有Agent的标准化输出格式
"""

import json
import logging
import json_repair
from typing import Dict, Any, Optional, List
from dataclasses import asdict, is_dataclass

from src.entity.states import (
    StandardOutput,
    SearchResult,
    AnalysisResult,
    VisualizationResult,
    ReportResult
)

logger = logging.getLogger(__name__)


def repair_json_output(content: str) -> str:
    """
    Repair and normalize JSON output.

    Args:
        content (str): String content that may contain JSON

    Returns:
        str: Repaired JSON string, or original content if not JSON
    """
    content = content.strip()
    if content.startswith(("{", "[")) or "```json" in content or "```ts" in content:
        try:
            # If content is wrapped in ```json code block, extract the JSON part
            if content.startswith("```json"):
                content = content.removeprefix("```json")

            if content.startswith("```ts"):
                content = content.removeprefix("```ts")

            if content.endswith("```"):
                content = content.removesuffix("```")

            # Try to repair and parse JSON
            repaired_content = json_repair.loads(content)
            return json.dumps(repaired_content, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"JSON repair failed: {e}")
    return content


def to_dict(obj: Any) -> Dict[str, Any]:
    """Convert dataclass or object to dictionary"""
    if is_dataclass(obj):
        return asdict(obj)
    elif hasattr(obj, '__dict__'):
        return dict(obj.__dict__)
    return obj


def to_json(obj: Any, indent: int = 2, ensure_ascii: bool = False) -> str:
    """Convert object to JSON string"""
    return json.dumps(to_dict(obj), indent=indent, ensure_ascii=ensure_ascii)


def create_search_result(
    success: bool = True,
    query_type: str = "",
    data_summary: Optional[Dict[str, Any]] = None,
    raw_data: Optional[str] = None,
    statistics: Optional[Dict[str, float]] = None,
    error_message: Optional[str] = None
) -> SearchResult:
    """
    Create standardized SearchResult (问数结果)
    
    Args:
        success: Whether the operation succeeded
        query_type: Type of query ("average", "comparison", "summary", "count")
        data_summary: Summary of the data retrieved
        raw_data: Raw data (optional)
        statistics: Key statistics from the data
        error_message: Error message if failed
    """
    return SearchResult(
        success=success,
        error_message=error_message,
        query_type=query_type,
        data_summary=data_summary or {},
        raw_data=raw_data,
        statistics=statistics or {}
    )


def create_analysis_result(
    success: bool = True,
    analysis_type: str = "",
    generated_code: str = "",
    code_executed: bool = False,
    execution_result: Optional[str] = None,
    model_metrics: Optional[Dict[str, Any]] = None,
    insights: Optional[List[str]] = None,
    error_message: Optional[str] = None
) -> AnalysisResult:
    """
    Create standardized AnalysisResult (分析建模结果)
    
    Args:
        success: Whether the operation succeeded
        analysis_type: Type of analysis ("correlation", "regression", "clustering", "trend", "multi_factor")
        generated_code: Python code generated (from autostat_modeling.md)
        code_executed: Whether code was executed
        execution_result: Result of code execution
        model_metrics: Model performance metrics
        insights: Key insights from the analysis
        error_message: Error message if failed
    """
    return AnalysisResult(
        success=success,
        error_message=error_message,
        analysis_type=analysis_type,
        generated_code=generated_code,
        code_executed=code_executed,
        execution_result=execution_result,
        model_metrics=model_metrics or {},
        insights=insights or []
    )


def create_visualization_result(
    success: bool = True,
    chart_type: str = "",
    chart_title: str = "",
    chart_path: Optional[str] = None,
    chart_base64: Optional[str] = None,
    variables_used: Optional[List[str]] = None,
    chart_description: str = "",
    generated_code: str = "",
    error_message: Optional[str] = None
) -> VisualizationResult:
    """
    Create standardized VisualizationResult (可视化结果)
    
    Args:
        success: Whether the operation succeeded
        chart_type: Type of chart ("bar", "line", "pie", "radar", "scatter", "heatmap")
        chart_title: Title of the chart
        chart_path: Path to saved chart file
        chart_base64: Base64 encoded chart (optional)
        variables_used: List of variables used in the chart
        chart_description: Description of what the chart shows
        generated_code: Python code generated (from autostat_visualization.md)
        error_message: Error message if failed
    """
    return VisualizationResult(
        success=success,
        error_message=error_message,
        chart_type=chart_type,
        chart_title=chart_title,
        chart_path=chart_path,
        chart_base64=chart_base64,
        variables_used=variables_used or [],
        chart_description=chart_description,
        generated_code=generated_code
    )


def create_report_result(
    success: bool = True,
    report_format: str = "",
    report_path: Optional[str] = None,
    report_content: str = "",
    sections_included: Optional[List[str]] = None,
    word_count: int = 0,
    error_message: Optional[str] = None
) -> ReportResult:
    """
    Create standardized ReportResult (报告结果)
    
    Args:
        success: Whether the operation succeeded
        report_format: Format of the report ("md", "word", "csv")
        report_path: Path to saved report file
        report_content: Full content of the report
        sections_included: List of sections included in the report
        word_count: Word count of the report
        error_message: Error message if failed
    """
    return ReportResult(
        success=success,
        error_message=error_message,
        report_format=report_format,
        report_path=report_path,
        report_content=report_content,
        sections_included=sections_included or [],
        word_count=word_count
    )


def format_output_for_frontend(result: Any) -> Dict[str, Any]:
    """
    Format output for frontend display
    将输出格式化为前端展示格式
    
    Returns:
        Dictionary with standardized fields for frontend
    """
    result_dict = to_dict(result)
    
    output = {
        "success": result_dict.get("success", True),
        "error_message": result_dict.get("error_message"),
        "timestamp": result_dict.get("timestamp"),
    }
    
    if isinstance(result, SearchResult):
        output.update({
            "type": "search",
            "query_type": result_dict.get("query_type"),
            "data_summary": result_dict.get("data_summary", {}),
            "statistics": result_dict.get("statistics", {}),
            "raw_data": result_dict.get("raw_data")
        })
    
    elif isinstance(result, AnalysisResult):
        output.update({
            "type": "analysis",
            "analysis_type": result_dict.get("analysis_type"),
            "generated_code": result_dict.get("generated_code", ""),
            "code_executed": result_dict.get("code_executed", False),
            "execution_result": result_dict.get("execution_result"),
            "model_metrics": result_dict.get("model_metrics", {}),
            "insights": result_dict.get("insights", [])
        })
    
    elif isinstance(result, VisualizationResult):
        output.update({
            "type": "visualization",
            "chart_type": result_dict.get("chart_type"),
            "chart_title": result_dict.get("chart_title"),
            "chart_path": result_dict.get("chart_path"),
            "chart_base64": result_dict.get("chart_base64"),
            "variables_used": result_dict.get("variables_used", []),
            "chart_description": result_dict.get("chart_description"),
            "generated_code": result_dict.get("generated_code", "")
        })
    
    elif isinstance(result, ReportResult):
        output.update({
            "type": "report",
            "report_format": result_dict.get("report_format"),
            "report_path": result_dict.get("report_path"),
            "report_content": result_dict.get("report_content", ""),
            "sections_included": result_dict.get("sections_included", []),
            "word_count": result_dict.get("word_count", 0)
        })
    
    return output


def validate_output(result: Any) -> bool:
    """
    Validate that output conforms to standards
    验证输出是否符合标准
    
    Returns:
        True if valid, False otherwise
    """
    try:
        if not isinstance(result, StandardOutput):
            logger.warning(f"Output is not a StandardOutput subclass: {type(result)}")
            return False
        
        result_dict = to_dict(result)
        
        if "success" not in result_dict:
            logger.warning("Output missing 'success' field")
            return False
        
        if "timestamp" not in result_dict:
            logger.warning("Output missing 'timestamp' field")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Output validation failed: {e}")
        return False
