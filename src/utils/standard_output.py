"""
标准化输出模块 - 定义前端展示所需的标准数据格式
"""
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class StandardOutput:
    """
    标准输出数据结构，完全符合前端展示要求
    """
    intent_recognition: Optional[Dict[str, Any]] = field(default_factory=dict)
    routing_log: Optional[str] = ""
    plan: List[Dict[str, Any]] = field(default_factory=list)
    execution_records: List[Dict[str, Any]] = field(default_factory=list)
    result_data: Dict[str, Any] = field(default_factory=dict)
    python_code: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def add_intent_recognition(self, intent_type: str, confidence: float, reasoning: str = ""):
        """添加意图识别结果"""
        self.intent_recognition = {
            "intent_type": intent_type,
            "confidence": confidence,
            "reasoning": reasoning
        }
    
    def add_routing_log(self, routing_info: str):
        """添加路由日志"""
        self.routing_log = routing_info
    
    def add_plan_step(self, step_id: int, action: str, agent: str):
        """添加计划步骤"""
        self.plan.append({
            "step_id": step_id,
            "action": action,
            "agent": agent
        })
    
    def add_execution_record(self, action: str, agent: str, execution_status: str, output: Dict[str, Any]):
        """添加执行记录"""
        self.execution_records.append({
            "action": action,
            "agent": agent,
            "execution_status": execution_status,
            "output": output
        })
    
    def set_result_data(self, data: Dict[str, Any]):
        """设置结果数据"""
        self.result_data = data
    
    def set_python_code(self, code: str):
        """设置 Python 代码"""
        self.python_code = code


def build_standard_output_from_state(state: Dict[str, Any]) -> StandardOutput:
    """
    从 PlanState 构建标准输出对象
    
    Args:
        state: PlanState 字典
        
    Returns:
        StandardOutput 对象
    """
    output = StandardOutput()
    
    # 1. 意图识别
    if state.get("intent_type"):
        output.add_intent_recognition(
            intent_type=state.get("intent_type", ""),
            confidence=state.get("intent_confidence", 0.0),
            reasoning=state.get("intent", "")
        )
        
        # 路由日志
        output.add_routing_log(
            f"src.graph.enhanced_builder - INFO - Routing based on intent: {state.get('intent_type')}"
        )
    
    # 2. 执行计划
    current_plan = state.get("current_plan")
    if current_plan:
        try:
            if hasattr(current_plan, 'model_dump'):
                plan_dict = current_plan.model_dump()
            elif hasattr(current_plan, '__dict__'):
                plan_dict = dict(current_plan.__dict__)
            else:
                plan_dict = current_plan
            
            # 提取步骤
            steps = plan_dict.get('steps', [])
            for i, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    step_id = step.get('step_id', i)
                    action = step.get('description', step.get('action', ''))
                    agent = step.get('agent', 'plan_agent')
                    output.add_plan_step(step_id, action, agent)
                else:
                    output.add_plan_step(i, str(step), 'plan_agent')
        except Exception as e:
            logger.warning(f"Failed to extract plan steps: {e}")
    
    # 3. 执行记录
    from src.entity.states import PlanState
    execution_records_json = PlanState.get_all_execution_records_json(state)
    if execution_records_json:
        for record_dict in execution_records_json:
            try:
                action = record_dict.get('step_name', record_dict.get('action', ''))
                agent = record_dict.get('tool_used', record_dict.get('agent', ''))
                execution_status = record_dict.get('execution_status', 'unknown')
                output_data = record_dict.get('result', record_dict.get('output', {}))
                
                # 确保 output 是字典格式
                if not isinstance(output_data, dict):
                    output_data = {"value": output_data}
                
                output.add_execution_record(action, agent, execution_status, output_data)
            except Exception as e:
                logger.warning(f"Failed to process execution record: {e}")
    
    # 4. 结果数据 - 收集所有 Agent 输出
    result_data = {}
    
    # 搜索结果
    search_result = state.get("search_result")
    if search_result:
        try:
            if hasattr(search_result, 'model_dump'):
                result_data['search'] = search_result.model_dump()
            elif hasattr(search_result, '__dict__'):
                result_data['search'] = dict(search_result.__dict__)
            else:
                result_data['search'] = search_result
        except Exception as e:
            logger.warning(f"Failed to serialize search result: {e}")
    
    # 分析结果
    analysis_result = state.get("analysis_result")
    if analysis_result:
        try:
            if hasattr(analysis_result, 'model_dump'):
                result_data['analysis'] = analysis_result.model_dump()
            elif hasattr(analysis_result, '__dict__'):
                result_data['analysis'] = dict(analysis_result.__dict__)
            else:
                result_data['analysis'] = analysis_result
        except Exception as e:
            logger.warning(f"Failed to serialize analysis result: {e}")
    
    # 可视化结果
    visualization_result = state.get("visualization_result")
    if visualization_result:
        try:
            if hasattr(visualization_result, 'model_dump'):
                result_data['visualization'] = visualization_result.model_dump()
            elif hasattr(visualization_result, '__dict__'):
                result_data['visualization'] = dict(visualization_result.__dict__)
            else:
                result_data['visualization'] = visualization_result
        except Exception as e:
            logger.warning(f"Failed to serialize visualization result: {e}")
    
    # 报告结果
    report_result = state.get("report_result")
    if report_result:
        try:
            if hasattr(report_result, 'model_dump'):
                result_data['report'] = report_result.model_dump()
            elif hasattr(report_result, '__dict__'):
                result_data['report'] = dict(report_result.__dict__)
            else:
                result_data['report'] = report_result
        except Exception as e:
            logger.warning(f"Failed to serialize report result: {e}")
    
    if result_data:
        output.set_result_data(result_data)
    
    # 5. Python 代码 - 收集所有生成的代码
    python_codes = []
    
    # 从生成的代码文件中收集
    generated_code_files = state.get("generated_code_files", [])
    if generated_code_files:
        for code_file in generated_code_files:
            try:
                if hasattr(code_file, 'code_content'):
                    python_codes.append(code_file.code_content)
                elif hasattr(code_file, '__dict__'):
                    code_dict = dict(code_file.__dict__)
                    if code_dict.get('code_content'):
                        python_codes.append(code_dict['code_content'])
            except Exception as e:
                logger.warning(f"Failed to extract code from file: {e}")
    
    # 从 Agent 结果中收集
    if analysis_result and hasattr(analysis_result, 'generated_code'):
        if analysis_result.generated_code:
            python_codes.append(analysis_result.generated_code)
    
    if visualization_result and hasattr(visualization_result, 'generated_code'):
        if visualization_result.generated_code:
            python_codes.append(visualization_result.generated_code)
    
    if state.get('generated_code'):
        python_codes.append(state.get('generated_code'))
    
    if python_codes:
        output.set_python_code('\n\n# ' + '='*50 + '\n\n'.join(python_codes))
    
    return output


def format_standard_output_for_frontend(output: StandardOutput) -> List[str]:
    """
    将 StandardOutput 格式化为前端可解析的格式
    
    Args:
        output: StandardOutput 对象
        
    Returns:
        前端可解析的消息列表
    """
    messages = []
    
    # 1. 意图识别（单独 JSON 块）
    if output.intent_recognition:
        intent_json = json.dumps(output.intent_recognition, ensure_ascii=False, indent=2)
        messages.append(f"```json\n{intent_json}\n```")
    
    # 2. 路由日志
    if output.routing_log:
        messages.append(output.routing_log)
    
    # 3. 执行计划（单独 JSON 块，包装在包含 steps 键的对象中）
    if output.plan:
        plan_wrapper = {"steps": output.plan}
        plan_json = json.dumps(plan_wrapper, ensure_ascii=False, indent=2)
        messages.append(f"```json\n{plan_json}\n```")
    
    # 4. 执行记录（每个记录一个 JSON 块）
    for record in output.execution_records:
        # 转换为前端期望的格式：添加 step_name 和 tool_used 字段
        record_formatted = record.copy()
        if 'action' in record_formatted and 'step_name' not in record_formatted:
            record_formatted['step_name'] = record_formatted['action']
        if 'agent' in record_formatted and 'tool_used' not in record_formatted:
            record_formatted['tool_used'] = record_formatted['agent']
        
        record_json = json.dumps(record_formatted, ensure_ascii=False, indent=2)
        messages.append(f"```json\n{record_json}\n```")
    
    # 5. 结果数据
    if output.result_data:
        result_json = json.dumps(output.result_data, ensure_ascii=False, indent=2)
        messages.append(f"```json\n{result_json}\n```")
    
    # 6. Python 代码
    if output.python_code:
        messages.append(f"```python\n{output.python_code}\n```")
    
    return messages
