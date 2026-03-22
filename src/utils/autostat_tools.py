"""
AutoSTAT工具适配器层 - 将AutoSTAT的专业功能包装为LangChain Tools
使用整合后的Markdown提示词文件
"""
import json
import logging
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from src.prompts.template import get_prompt_without_render

logger = logging.getLogger(__name__)


@tool
def autostat_get_preprocessing_suggestions(
    df_info: str,
    user_input: Optional[str] = None
) -> str:
    """
    获取AutoSTAT风格的数据预处理建议。
    
    Args:
        df_info: DataFrame信息字符串，包含数据规模、列信息等
        user_input: 可选的用户特定需求
    
    Returns:
        结构化的预处理建议提示词
    """
    prompt = get_prompt_without_render("autostat_preprocessing")
    
    if user_input:
        prompt += f"\n\n=== User Specific Requirements ===\n{user_input}"
    
    prompt += f"\n\n=== Provided Data Information ===\n{df_info}"
    
    return prompt


@tool
def autostat_generate_preprocessing_code(
    df_head: str,
    user_prompt: str,
    allowed_libs: Optional[str] = None
) -> str:
    """
    生成AutoSTAT风格的数据预处理代码。
    
    Args:
        df_head: DataFrame前几行的字符串表示
        user_prompt: 用户的预处理需求
        allowed_libs: 允许使用的库列表
    
    Returns:
        可执行的Python预处理代码提示词
    """
    base_prompt = get_prompt_without_render("autostat_preprocessing")
    
    allowed = allowed_libs or "numpy, pandas, sklearn.impute, sklearn.preprocessing, sklearn.compose, sklearn.pipeline"
    
    prompt = f"""{base_prompt}

=== ADDITIONAL CODE GENERATION REQUIREMENTS ===

Allowed libraries: {allowed}

=== Input Data Sample ===
{df_head}

=== User Specification ===
{user_prompt}

Please output complete, executable Python code following all the above requirements.
"""
    
    return prompt


@tool
def autostat_get_modeling_suggestions(
    df_info: str,
    user_input: Optional[str] = None,
    target: Optional[str] = None
) -> str:
    """
    获取AutoSTAT风格的建模建议。
    
    Args:
        df_info: DataFrame信息字符串
        user_input: 可选的用户特定需求
        target: 可选的建模目标变量
    
    Returns:
        结构化的建模建议提示词
    """
    prompt = get_prompt_without_render("autostat_modeling")
    
    prompt += f"\n\n=== Data Information ===\n{df_info}"
    
    if target:
        prompt += f"\n\n=== Modeling Target ===\n{target}"
    
    if user_input:
        prompt += f"\n\n=== User Requirements ===\n{user_input}"
    
    return prompt


@tool
def autostat_generate_modeling_code(
    df_head: str,
    user_prompt: str,
    allowed_libs: Optional[str] = None
) -> str:
    """
    生成AutoSTAT风格的建模代码。
    
    Args:
        df_head: DataFrame前几行的字符串表示
        user_prompt: 用户的建模需求
        allowed_libs: 允许使用的库列表
    
    Returns:
        可执行的Python建模代码提示词
    """
    base_prompt = get_prompt_without_render("autostat_modeling")
    
    allowed = allowed_libs or "numpy, sklearn.model_selection, sklearn.preprocessing, sklearn.ensemble, xgboost, lightgbm"
    
    prompt = f"""{base_prompt}

=== ADDITIONAL CODE GENERATION REQUIREMENTS ===

Allowed libraries: {allowed}

=== Sample Data Header ===
{df_head}

=== Requirement ===
{user_prompt}

Please output complete, executable Python code following all the above requirements.
"""
    
    return prompt


@tool
def autostat_format_modeling_results(
    result_json: str
) -> str:
    """
    格式化AutoSTAT风格的建模结果为Markdown报告。
    
    Args:
        result_json: 建模结果的JSON字符串
    
    Returns:
        Markdown格式的结果报告提示词
    """
    prompt = get_prompt_without_render("autostat_modeling")
    
    prompt += f"\n\n=== Input JSON Results ===\n{result_json}"
    
    prompt += "\n\nPlease format these results into a human-friendly Markdown report following the requirements above."
    
    return prompt


@tool
def autostat_suggest_charts(
    df_info: str,
    user_input: Optional[str] = None
) -> str:
    """
    获取AutoSTAT风格的可视化建议。
    
    Args:
        df_info: DataFrame信息字符串
        user_input: 可选的用户特定需求
    
    Returns:
        结构化的图表建议提示词
    """
    prompt = get_prompt_without_render("autostat_visualization")
    
    prompt += f"\n\n=== Dataset Information ===\n{df_info}"
    
    if user_input:
        prompt += f"\n\n=== User Requirements ===\n{user_input}"
    
    return prompt


@tool
def autostat_generate_visualization_code(
    df_head: str,
    chart_suggestions: str,
    user_input: Optional[str] = None,
    color: Optional[str] = None
) -> str:
    """
    生成AutoSTAT风格的可视化代码。
    
    Args:
        df_head: DataFrame前几行的字符串表示
        chart_suggestions: 图表建议
        user_input: 可选的用户特定需求
        color: 可选的颜色方案
    
    Returns:
        可执行的Python可视化代码提示词
    """
    base_prompt = get_prompt_without_render("autostat_visualization")
    
    prompt = f"""{base_prompt}

=== ADDITIONAL CODE GENERATION REQUIREMENTS ===

=== Example Data Header ===
{df_head}

=== Chart Suggestions ===
{chart_suggestions}
"""
    
    if color:
        prompt += f"\n=== Color Scheme ===\n{color}"
    
    if user_input:
        prompt += f"\n=== User Requirements ===\n{user_input}"
    
    prompt += "\n\nPlease output complete, executable Python code following all the above requirements."
    
    return prompt


@tool
def autostat_generate_markdown_report(
    analysis_results: Dict[str, Any],
    report_title: Optional[str] = "数据分析报告"
) -> str:
    """
    生成AutoSTAT风格的Markdown报告。
    
    Args:
        analysis_results: 分析结果字典
        report_title: 报告标题
    
    Returns:
        Markdown格式的报告提示词
    """
    prompt = get_prompt_without_render("autostat_report")
    
    prompt += f"\n\n=== Report Title ===\n{report_title}"
    prompt += f"\n\n=== Analysis Results ===\n{json.dumps(analysis_results, ensure_ascii=False, indent=2)}"
    
    prompt += "\n\nPlease generate a comprehensive Markdown report based on the above information."
    
    return prompt


@tool
def autostat_generate_toc(
    full_summary: str,
    outline_length: Optional[str] = "standard"
) -> str:
    """
    生成AutoSTAT风格的报告目录。
    
    Args:
        full_summary: 报告完整摘要
        outline_length: 目录详细程度 (brief/standard/detailed)
    
    Returns:
        目录生成提示词
    """
    prompt = get_prompt_without_render("autostat_report")
    
    prompt += f"\n\n=== User Selected Detail Level ===\n{outline_length}"
    prompt += f"\n\n=== Report Summary ===\n{full_summary}"
    
    prompt += "\n\nPlease generate a table of contents following the requirements above."
    
    return prompt


@tool
def autostat_write_report_section(
    current_section: str,
    toc: str,
    reference_content: str,
    history_content: Optional[str] = None,
    writing_mode: Optional[str] = "standard"
) -> str:
    """
    撰写AutoSTAT风格的报告章节。
    
    Args:
        current_section: 当前章节信息
        toc: 完整目录结构
        reference_content: 参考分析内容
        history_content: 可选的历史生成内容
        writing_mode: 写作模式 (brief/standard/detailed)
    
    Returns:
        章节撰写提示词
    """
    prompt = get_prompt_without_render("autostat_report")
    
    prompt += f"\n\n=== Current Section ===\n{current_section}"
    prompt += f"\n\n=== Full TOC Structure ===\n{toc}"
    prompt += f"\n\n=== Reference Content ===\n{reference_content}"
    
    if history_content:
        prompt += f"\n\n=== Previously Generated Content ===\n{history_content}"
    
    prompt += f"\n\n=== Writing Mode ===\n{writing_mode}"
    
    prompt += "\n\nPlease write the report section following the requirements above."
    
    return prompt
