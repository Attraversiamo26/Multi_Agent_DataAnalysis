"""
结果验证器 - 验证和修复 JSON 输出
"""
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ResultValidator:
    """结果验证器，确保 JSON 输出符合规范"""
    
    # JSON Schema 定义
    SCHEMA = {
        "type": "object",
        "required": ["summary", "intent_recognition", "execution_summary", "result_data"],
        "properties": {
            "summary": {
                "type": "object",
                "required": ["task_completed", "total_steps", "successful_steps", "execution_time_seconds"],
                "properties": {
                    "task_completed": {"type": "boolean"},
                    "total_steps": {"type": "integer", "minimum": 0},
                    "successful_steps": {"type": "integer", "minimum": 0},
                    "execution_time_seconds": {"type": "number", "minimum": 0}
                }
            },
            "intent_recognition": {
                "type": "object",
                "required": ["intent_type", "confidence", "reasoning"],
                "properties": {
                    "intent_type": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "reasoning": {"type": "string"}
                }
            },
            "execution_summary": {
                "type": "object",
                "required": ["total_records", "steps"],
                "properties": {
                    "total_records": {"type": "integer", "minimum": 0},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["step_index", "action", "agent", "status"],
                            "properties": {
                                "step_index": {"type": "integer", "minimum": 1},
                                "action": {"type": "string"},
                                "agent": {"type": "string"},
                                "status": {"type": "string", "enum": ["success", "failed", "skipped", "unknown"]},
                                "output": {"type": "object"},
                                "execution_time": {"type": "number"}
                            }
                        }
                    }
                }
            },
            "result_data": {
                "type": "object",
                "properties": {
                    "search_results": {"type": "object"},
                    "analysis_results": {"type": "object"},
                    "visualization_results": {"type": "object"},
                    "tabular_data": {"type": "object"}
                }
            },
            "python_code": {
                "type": "object",
                "properties": {
                    "scripts": {"type": "array", "items": {"type": "string"}},
                    "code_files": {"type": "array", "items": {"type": "string"}}
                }
            },
            "routing_log": {"type": "string"},
            "recommendations": {"type": "array", "items": {"type": "string"}},
            "next_steps": {"type": "array", "items": {"type": "string"}}
        }
    }
    
    # 大小限制（字节）
    MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB
    MAX_STRING_LENGTH = 10000
    MAX_LIST_LENGTH = 100
    MAX_DICT_SIZE = 100  # 键值对数量
    
    @classmethod
    def validate(cls, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证数据是否符合规范
        
        Args:
            data: 待验证的数据字典
            
        Returns:
            (是否通过验证，错误信息列表)
        """
        errors = []
        warnings = []
        
        # 1. 检查是否为字典
        if not isinstance(data, dict):
            errors.append("Output must be a dictionary")
            return False, errors
        
        # 2. 检查必填字段
        required_fields = cls.SCHEMA["required"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # 3. 验证各字段
        if 'summary' in data:
            cls._validate_summary(data['summary'], errors, warnings)
        
        if 'intent_recognition' in data:
            cls._validate_intent_recognition(data['intent_recognition'], errors, warnings)
        
        if 'execution_summary' in data:
            cls._validate_execution_summary(data['execution_summary'], errors, warnings)
        
        if 'result_data' in data:
            cls._validate_result_data(data['result_data'], errors, warnings)
        
        if 'python_code' in data:
            cls._validate_python_code(data['python_code'], errors, warnings)
        
        # 4. 检查大小限制
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            if len(json_str) > cls.MAX_OUTPUT_SIZE:
                errors.append(f"Output size ({len(json_str)} bytes) exceeds limit ({cls.MAX_OUTPUT_SIZE} bytes)")
        except Exception as e:
            errors.append(f"JSON serialization failed: {str(e)}")
        
        # 5. 记录警告
        for warning in warnings:
            logger.warning(f"[ResultValidator] {warning}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    @classmethod
    def _validate_summary(cls, summary: Dict, errors: List[str], warnings: List[str]):
        """验证 summary 字段"""
        if not isinstance(summary, dict):
            errors.append("summary must be a dictionary")
            return
        
        required = ['task_completed', 'total_steps', 'successful_steps', 'execution_time_seconds']
        for field in required:
            if field not in summary:
                errors.append(f"Missing required field in summary: {field}")
        
        # 类型检查
        if 'task_completed' in summary and not isinstance(summary['task_completed'], bool):
            errors.append("summary.task_completed must be a boolean")
        
        if 'total_steps' in summary:
            if not isinstance(summary['total_steps'], (int, float)):
                errors.append("summary.total_steps must be a number")
            elif summary['total_steps'] < 0:
                errors.append("summary.total_steps must be non-negative")
        
        if 'successful_steps' in summary:
            if not isinstance(summary['successful_steps'], (int, float)):
                errors.append("summary.successful_steps must be a number")
            elif summary['successful_steps'] < 0:
                errors.append("summary.successful_steps must be non-negative")
        
        # 逻辑检查
        if 'total_steps' in summary and 'successful_steps' in summary:
            if summary['successful_steps'] > summary['total_steps']:
                warnings.append("successful_steps > total_steps")
    
    @classmethod
    def _validate_intent_recognition(cls, intent: Dict, errors: List[str], warnings: List[str]):
        """验证 intent_recognition 字段"""
        if not isinstance(intent, dict):
            errors.append("intent_recognition must be a dictionary")
            return
        
        required = ['intent_type', 'confidence', 'reasoning']
        for field in required:
            if field not in intent:
                errors.append(f"Missing required field in intent_recognition: {field}")
        
        # 类型检查
        if 'intent_type' in intent and not isinstance(intent['intent_type'], str):
            errors.append("intent_recognition.intent_type must be a string")
        
        if 'confidence' in intent:
            if not isinstance(intent['confidence'], (int, float)):
                errors.append("intent_recognition.confidence must be a number")
            elif not (0.0 <= intent['confidence'] <= 1.0):
                errors.append("intent_recognition.confidence must be between 0.0 and 1.0")
    
    @classmethod
    def _validate_execution_summary(cls, exec_summary: Dict, errors: List[str], warnings: List[str]):
        """验证 execution_summary 字段"""
        if not isinstance(exec_summary, dict):
            errors.append("execution_summary must be a dictionary")
            return
        
        required = ['total_records', 'steps']
        for field in required:
            if field not in exec_summary:
                errors.append(f"Missing required field in execution_summary: {field}")
        
        # 验证 steps
        if 'steps' in exec_summary:
            if not isinstance(exec_summary['steps'], list):
                errors.append("execution_summary.steps must be a list")
            else:
                for i, step in enumerate(exec_summary['steps']):
                    cls._validate_step(step, i, errors, warnings)
    
    @classmethod
    def _validate_step(cls, step: Dict, index: int, errors: List[str], warnings: List[str]):
        """验证单个步骤"""
        if not isinstance(step, dict):
            errors.append(f"Step {index} must be a dictionary")
            return
        
        required = ['step_index', 'action', 'agent', 'status']
        for field in required:
            if field not in step:
                errors.append(f"Step {index} missing required field: {field}")
        
        # 状态检查
        if 'status' in step:
            valid_statuses = ['success', 'failed', 'skipped', 'unknown']
            if step['status'] not in valid_statuses:
                warnings.append(f"Step {index} has unusual status: {step['status']}")
    
    @classmethod
    def _validate_result_data(cls, result_data: Dict, errors: List[str], warnings: List[str]):
        """验证 result_data 字段"""
        if not isinstance(result_data, dict):
            errors.append("result_data must be a dictionary")
            return
        
        # 检查子字段
        valid_keys = ['search_results', 'analysis_results', 'visualization_results', 'tabular_data']
        for key in result_data:
            if key not in valid_keys:
                warnings.append(f"result_data has unexpected field: {key}")
    
    @classmethod
    def _validate_python_code(cls, python_code: Dict, errors: List[str], warnings: List[str]):
        """验证 python_code 字段"""
        if not isinstance(python_code, dict):
            errors.append("python_code must be a dictionary")
            return
        
        # 验证 scripts
        if 'scripts' in python_code:
            if not isinstance(python_code['scripts'], list):
                errors.append("python_code.scripts must be a list")
            else:
                for i, script in enumerate(python_code['scripts']):
                    if not isinstance(script, str):
                        errors.append(f"python_code.scripts[{i}] must be a string")
        
        # 验证 code_files
        if 'code_files' in python_code:
            if not isinstance(python_code['code_files'], list):
                errors.append("python_code.code_files must be a list")
            else:
                for i, file_path in enumerate(python_code['code_files']):
                    if not isinstance(file_path, str):
                        errors.append(f"python_code.code_files[{i}] must be a string")
    
    @classmethod
    def sanitize(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理数据，确保可以 JSON 序列化且不超过大小限制
        
        Args:
            data: 原始数据
            
        Returns:
            清理后的数据
        """
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        
        for key, value in data.items():
            # 递归清理
            if isinstance(value, dict):
                sanitized[key] = cls.sanitize(value)
            elif isinstance(value, list):
                # 限制列表长度
                if len(value) > cls.MAX_LIST_LENGTH:
                    sanitized[key] = value[:cls.MAX_LIST_LENGTH] + ["... [truncated]"]
                else:
                    sanitized[key] = [cls.sanitize(item) for item in value]
            elif isinstance(value, str):
                # 限制字符串长度
                if len(value) > cls.MAX_STRING_LENGTH:
                    sanitized[key] = value[:cls.MAX_STRING_LENGTH] + "... [truncated]"
                else:
                    sanitized[key] = value
            elif isinstance(value, (int, float, bool, type(None))):
                sanitized[key] = value
            else:
                # 其他类型转换为字符串
                sanitized[key] = str(value)
        
        return sanitized
    
    @classmethod
    def fix(cls, data: Dict[str, Any], errors: List[str]) -> Dict[str, Any]:
        """
        尝试修复验证错误
        
        Args:
            data: 原始数据
            errors: 验证错误列表
            
        Returns:
            修复后的数据
        """
        fixed_data = data.copy()
        
        for error in errors:
            # 修复缺失的必填字段
            if "Missing required field" in error:
                field_name = error.split(": ")[-1]
                
                if field_name == "summary":
                    fixed_data['summary'] = {
                        "task_completed": True,
                        "total_steps": 0,
                        "successful_steps": 0,
                        "execution_time_seconds": 0.0
                    }
                elif field_name == "intent_recognition":
                    fixed_data['intent_recognition'] = {
                        "intent_type": "UNKNOWN",
                        "confidence": 0.0,
                        "reasoning": ""
                    }
                elif field_name == "execution_summary":
                    fixed_data['execution_summary'] = {
                        "total_records": 0,
                        "steps": []
                    }
                elif field_name == "result_data":
                    fixed_data['result_data'] = {}
        
        # 再次清理和验证
        fixed_data = cls.sanitize(fixed_data)
        
        return fixed_data
    
    @classmethod
    def to_json(cls, data: Dict[str, Any], indent: int = 2) -> str:
        """
        将数据转换为 JSON 字符串
        
        Args:
            data: 数据字典
            indent: JSON 缩进空格数
            
        Returns:
            JSON 字符串
        """
        return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
