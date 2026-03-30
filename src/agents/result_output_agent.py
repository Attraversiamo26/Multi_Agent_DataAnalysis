"""
结果输出 Agent - 负责整合多源数据并输出标准化 JSON 结果
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage

from src.agents.react_agent_base import ReActAgentBase
from src.entity.states import StepState
from src.utils.tools import terminate
from src.prompts.template import apply_prompt_template
from src.utils.result_validator import ResultValidator

logger = logging.getLogger(__name__)


class ResultOutputAgent(ReActAgentBase):
    """结果输出 Agent，整合多源数据并输出标准化 JSON"""
    
    def __init__(self, agent_name: str = "result_output_agent"):
        super().__init__(
            agent_name=agent_name,
            react_llm="plan_agent",
            max_iterations=1  # 只需要一次迭代，因为不需要 ReAct 循环
        )
        self.retrieve_info = 'None available'
        self.workspace_directory = ""
        self.current_step = None
        self.tools = [terminate]  # 手动设置 tools
    
    def run(self, state: StepState, config):
        """执行结果输出 Agent"""
        from langchain_core.runnables import RunnableConfig
        
        logger.info(f"[{self.agent_name}] Starting result output aggregation")
        
        # 从状态中提取各 Agent 的结果
        search_result = state.get("search_result")
        analysis_result = state.get("analysis_result")
        visualization_result = state.get("visualization_result")
        report_result = state.get("report_result")
        execution_records = state.get("execution_records", [])
        generated_code_files = state.get("generated_code_files", [])
        intent_type = state.get("intent_type", "")
        intent_confidence = state.get("intent_confidence", 0.0)
        intent_reasoning = state.get("intent", "")
        current_plan = state.get("current_plan")
        
        # 整合数据并生成标准化输出
        standardized_output = self._create_standardized_output(
            search_result=search_result,
            analysis_result=analysis_result,
            visualization_result=visualization_result,
            report_result=report_result,
            execution_records=execution_records,
            generated_code_files=generated_code_files,
            intent_type=intent_type,
            intent_confidence=intent_confidence,
            intent_reasoning=intent_reasoning,
            current_plan=current_plan,
            state=state
        )
        
        # 使用 ResultValidator 验证输出
        is_valid, errors = ResultValidator.validate(standardized_output)
        
        if not is_valid:
            logger.warning(f"[{self.agent_name}] Output validation failed: {errors}")
            # 尝试修复
            standardized_output = ResultValidator.fix(standardized_output, errors)
            
            # 再次验证
            is_valid, errors = ResultValidator.validate(standardized_output)
            if is_valid:
                logger.info(f"[{self.agent_name}] Output validation passed after fix")
            else:
                logger.error(f"[{self.agent_name}] Output validation still failed after fix: {errors}")
        
        # 清理输出，确保大小合适
        standardized_output = ResultValidator.sanitize(standardized_output)
        
        # 添加到消息历史
        output_message = AIMessage(
            content=json.dumps(standardized_output, ensure_ascii=False, indent=2),
            id=f"result_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        if 'messages' not in state:
            state['messages'] = []
        state['messages'].append(output_message)
        
        logger.info(f"[{self.agent_name}] Result output completed successfully")
        
        return {
            "messages": state['messages'],
            "standardized_output": standardized_output
        }
    
    def _create_standardized_output(
        self,
        search_result: Any,
        analysis_result: Any,
        visualization_result: Any,
        report_result: Any,
        execution_records: List,
        generated_code_files: List,
        intent_type: str,
        intent_confidence: float,
        intent_reasoning: str,
        current_plan: Any,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建标准化输出"""
        
        # 1. 任务摘要
        summary = self._create_summary(execution_records, state)
        
        # 2. 意图识别
        intent_recognition = {
            "intent_type": intent_type or "UNKNOWN",
            "confidence": float(intent_confidence) if intent_confidence else 0.0,
            "reasoning": intent_reasoning or ""
        }
        
        # 3. 执行摘要
        execution_summary = self._create_execution_summary(execution_records)
        
        # 4. 结果数据
        result_data = {
            "search_results": self._process_search_result(search_result),
            "analysis_results": self._process_analysis_result(analysis_result),
            "visualization_results": self._process_visualization_result(visualization_result),
            "tabular_data": self._extract_tabular_data(
                search_result, analysis_result, visualization_result, execution_records
            )
        }
        
        # 5. Python 代码
        python_code = self._extract_python_code(generated_code_files, execution_records)
        
        # 6. 路由日志
        routing_log = state.get("routing_log", "")
        if not routing_log and intent_type:
            routing_log = f"src.graph.enhanced_builder - INFO - Routing based on intent: {intent_type}"
        
        # 7. 建议和后续步骤
        recommendations = self._generate_recommendations(analysis_result, execution_records)
        next_steps = self._suggest_next_steps(execution_records, current_plan)
        
        # 组装完整输出
        standardized_output = {
            "summary": summary,
            "intent_recognition": intent_recognition,
            "execution_summary": execution_summary,
            "result_data": result_data,
            "python_code": python_code,
            "routing_log": routing_log,
            "recommendations": recommendations,
            "next_steps": next_steps
        }
        
        return standardized_output
    
    def _create_summary(self, execution_records: List, state: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务摘要"""
        total_steps = len(execution_records) if execution_records else 0
        successful_steps = sum(
            1 for record in execution_records 
            if record.get('execution_status') == 'success'
        ) if execution_records else 0
        
        # 计算执行时间
        execution_time = 0.0
        if execution_records:
            for record in execution_records:
                if isinstance(record, dict):
                    execution_time += float(record.get('duration_seconds', 0.0) or 0.0)
        
        # 判断任务是否完成
        task_completed = successful_steps > 0 or state.get('overall_status') == 'success'
        
        return {
            "task_completed": bool(task_completed),
            "total_steps": total_steps,
            "successful_steps": successful_steps,
            "execution_time_seconds": round(execution_time, 2)
        }
    
    def _create_execution_summary(self, execution_records: List) -> Dict[str, Any]:
        """创建执行摘要"""
        steps = []
        
        if execution_records:
            for idx, record in enumerate(execution_records, 1):
                if isinstance(record, dict):
                    step = {
                        "step_index": idx,
                        "action": record.get('step_name', record.get('action', 'Unknown')),
                        "agent": record.get('tool_used', record.get('agent', 'unknown')),
                        "status": record.get('execution_status', 'unknown'),
                        "output": self._sanitize_output(record.get('result', record.get('output', {}))),
                        "execution_time": float(record.get('duration_seconds', 0.0) or 0.0)
                    }
                    steps.append(step)
        
        return {
            "total_records": len(steps),
            "steps": steps
        }
    
    def _process_search_result(self, search_result: Any) -> Dict[str, Any]:
        """处理搜索结果"""
        if not search_result:
            return {
                "total_count": 0,
                "statistics": {},
                "data_summary": {}
            }
        
        # 如果是 dataclass 对象，转换为字典
        if hasattr(search_result, 'model_dump'):
            result_dict = search_result.model_dump()
        elif hasattr(search_result, '__dict__'):
            result_dict = search_result.__dict__
        elif isinstance(search_result, dict):
            result_dict = search_result
        else:
            result_dict = {"raw_data": str(search_result)}
        
        return {
            "total_count": result_dict.get('total_count', result_dict.get('row_count', 0)),
            "statistics": result_dict.get('statistics', {}),
            "data_summary": self._sanitize_data(result_dict.get('data_summary', result_dict.get('raw_data', {})))
        }
    
    def _process_analysis_result(self, analysis_result: Any) -> Dict[str, Any]:
        """处理分析结果"""
        if not analysis_result:
            return {
                "metrics": {},
                "insights": [],
                "computed_values": {}
            }
        
        # 如果是 dataclass 对象，转换为字典
        if hasattr(analysis_result, 'model_dump'):
            result_dict = analysis_result.model_dump()
        elif hasattr(analysis_result, '__dict__'):
            result_dict = analysis_result.__dict__
        elif isinstance(analysis_result, dict):
            result_dict = analysis_result
        else:
            result_dict = {"raw_data": str(analysis_result)}
        
        return {
            "metrics": result_dict.get('model_metrics', result_dict.get('metrics', {})),
            "insights": result_dict.get('insights', []),
            "computed_values": result_dict.get('execution_result', result_dict.get('computed_values', {}))
        }
    
    def _process_visualization_result(self, visualization_result: Any) -> Dict[str, Any]:
        """处理可视化结果"""
        if not visualization_result:
            return {
                "charts": [],
                "chart_data": {},
                "descriptions": []
            }
        
        # 如果是 dataclass 对象，转换为字典
        if hasattr(visualization_result, 'model_dump'):
            result_dict = visualization_result.model_dump()
        elif hasattr(visualization_result, '__dict__'):
            result_dict = visualization_result.__dict__
        elif isinstance(visualization_result, dict):
            result_dict = visualization_result
        else:
            result_dict = {"raw_data": str(visualization_result)}
        
        return {
            "charts": [
                {
                    "type": result_dict.get('chart_type', 'unknown'),
                    "title": result_dict.get('chart_title', ''),
                    "description": result_dict.get('chart_description', '')
                }
            ],
            "chart_data": {},  # 图表数据通常较大，不直接包含
            "descriptions": [result_dict.get('chart_description', '')]
        }
    
    def _extract_tabular_data(self, search_result: Any, analysis_result: Any, 
                             visualization_result: Any, execution_records: List) -> Dict[str, Any]:
        """提取表格数据"""
        tables = []
        
        # 从各结果中提取表格数据
        for result in [search_result, analysis_result, visualization_result]:
            if result:
                if hasattr(result, 'model_dump'):
                    result_dict = result.model_dump()
                elif hasattr(result, '__dict__'):
                    result_dict = result.__dict__
                else:
                    result_dict = result
                
                # 查找可能的表格数据
                for key in ['data', 'records', 'items', 'results', 'table_data']:
                    if key in result_dict:
                        data = result_dict[key]
                        if isinstance(data, list) and len(data) > 0:
                            if isinstance(data[0], dict):
                                tables.append({
                                    "name": key,
                                    "data": self._sanitize_data(data),
                                    "row_count": len(data)
                                })
        
        # 从执行记录中提取
        for record in execution_records:
            if isinstance(record, dict):
                output = record.get('output', {}) or record.get('result', {})
                if isinstance(output, dict):
                    for key in ['data', 'records', 'items', 'results']:
                        if key in output:
                            data = output[key]
                            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                                tables.append({
                                    "name": f"{record.get('action', 'step')}_{key}",
                                    "data": self._sanitize_data(data),
                                    "row_count": len(data)
                                })
        
        return {
            "tables": tables,
            "metadata": {
                "total_tables": len(tables),
                "extraction_time": datetime.now().isoformat()
            }
        }
    
    def _extract_python_code(self, generated_code_files: List, execution_records: List) -> Dict[str, Any]:
        """提取 Python 代码"""
        scripts = []
        code_files = []
        
        # 从生成的代码文件中提取
        if generated_code_files:
            for code_file in generated_code_files:
                if hasattr(code_file, 'to_dict'):
                    code_dict = code_file.to_dict()
                elif hasattr(code_file, '__dict__'):
                    code_dict = code_file.__dict__
                else:
                    code_dict = code_file
                
                if code_dict.get('code_content'):
                    scripts.append(code_dict['code_content'])
                if code_dict.get('filename'):
                    code_files.append(code_dict.get('file_path', code_dict['filename']))
        
        # 从执行记录中提取 run_python_code 的 arguments
        if execution_records:
            for record in execution_records:
                if isinstance(record, dict):
                    output = record.get('output', {})
                    if isinstance(output, dict) and 'arguments' in output:
                        args = output['arguments']
                        if isinstance(args, dict) and 'code' in args:
                            scripts.append(args['code'])
        
        return {
            "scripts": scripts,
            "code_files": code_files
        }
    
    def _generate_recommendations(self, analysis_result: Any, execution_records: List) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于分析结果生成建议
        if analysis_result:
            if hasattr(analysis_result, 'insights') and analysis_result.insights:
                for insight in analysis_result.insights:
                    recommendations.append(f"基于分析发现：{insight}")
        
        # 基于执行情况生成建议
        if execution_records:
            failed_steps = [
                r for r in execution_records 
                if isinstance(r, dict) and r.get('execution_status') == 'failed'
            ]
            if failed_steps:
                recommendations.append("部分步骤执行失败，建议检查数据源或调整分析方法")
        
        if not recommendations:
            recommendations.append("分析已完成，可以基于结果进行进一步探索")
        
        return recommendations
    
    def _suggest_next_steps(self, execution_records: List, current_plan: Any) -> List[str]:
        """建议后续步骤"""
        next_steps = []
        
        # 如果有未完成的计划步骤
        if current_plan:
            if hasattr(current_plan, 'steps'):
                planned_steps = current_plan.steps
                executed_count = len(execution_records) if execution_records else 0
                
                if executed_count < len(planned_steps):
                    next_steps.append("继续执行计划中的剩余步骤")
        
        # 基于分析结果建议
        if execution_records:
            last_action = execution_records[-1].get('action', '') if execution_records else ''
            if '统计' in last_action or '分析' in last_action:
                next_steps.append("可以进行可视化展示")
            elif '可视化' in last_action:
                next_steps.append("可以生成综合报告")
        
        if not next_steps:
            next_steps.append("任务已完成，可以提出新的分析问题")
        
        return next_steps
    
    def _sanitize_output(self, output: Any) -> Any:
        """清理输出，移除过大的数据"""
        if output is None:
            return None
        
        if isinstance(output, str):
            # 如果字符串过长，截断
            if len(output) > 10000:
                return output[:10000] + "... [truncated]"
            return output
        
        if isinstance(output, (int, float, bool)):
            return output
        
        if isinstance(output, list):
            # 限制列表长度
            if len(output) > 100:
                return output[:100] + ["... [truncated]"]
            return [self._sanitize_output(item) for item in output]
        
        if isinstance(output, dict):
            sanitized = {}
            for key, value in output.items():
                # 跳过可能过大的字段
                if any(keyword in str(key).lower() for keyword in ['data', 'content', 'raw']):
                    if isinstance(value, str) and len(value) > 1000:
                        sanitized[key] = f"[Summary] {len(value)} characters"
                    elif isinstance(value, list) and len(value) > 50:
                        sanitized[key] = f"[Summary] {len(value)} items"
                    else:
                        sanitized[key] = self._sanitize_output(value)
                else:
                    sanitized[key] = self._sanitize_output(value)
            return sanitized
        
        return str(output)
    
    def _sanitize_data(self, data: Any) -> Any:
        """清理数据，确保可以 JSON 序列化"""
        if data is None:
            return None
        
        if isinstance(data, str):
            return data
        
        if isinstance(data, (int, float, bool)):
            return data
        
        if isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        
        if isinstance(data, dict):
            return {str(k): self._sanitize_data(v) for k, v in data.items()}
        
        # 其他类型转换为字符串
        return str(data)
    

