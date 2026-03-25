import logging
import json
import re
from typing import Dict, Any, Tuple, Optional

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message
from langgraph.types import Command

from src.entity.states import PlanState
from src.llms.llm import get_llm_by_name
from src.prompts.template import apply_prompt_template
from src.utils.llm_utils import astream
from src.utils.tag_manager import tag_scope, MessageTag

logger = logging.getLogger(__name__)


class EnhancedIntentRecognitionAgent:
    """增强版意图识别Agent，具有更高的准确率和验证机制"""
    
    VALID_INTENTS = ['SMALLTALK', 'ASK_DATA', 'ANALYSIS_MODELING', 'VISUALIZATION', 'REPORT']
    
    # 关键词映射表，用于快速意图识别
    KEYWORD_MAPS = {
        'SMALLTALK': [
            '你好', 'hello', 'hi', '早上好', '下午好', '晚上好',
            '你是谁', 'what is your name', '你叫什么',
            '谢谢', 'thank', 'thanks',
            '再见', 'bye', 'goodbye'
        ],
        'ASK_DATA': [
            '多少', '平均值', '总和', '总数', '数量', '最大', '最小',
            'average', 'sum', 'total', 'count', 'max', 'min',
            '对比', '比较', 'compare', 'which is higher',
            '显示', 'show', '展示', '查询', 'query'
        ],
        'ANALYSIS_MODELING': [
            '分析', 'analysis', 'analyze',
            '相关', 'correlation', '关联',
            '回归', 'regression',
            '预测', 'forecast', 'predict',
            '聚类', 'cluster', 'segmentation',
            '趋势', 'trend',
            '假设检验', 'hypothesis',
            '建模', 'modeling'
        ],
        'VISUALIZATION': [
            '图表', 'chart', '图',
            '柱状图', 'bar chart',
            '折线图', 'line chart',
            '饼图', 'pie chart',
            '散点图', 'scatter',
            '可视化', 'visualize', 'visualization',
            '绘制', 'plot', 'draw'
        ],
        'REPORT': [
            '报告', 'report',
            '文档', 'document', 'word',
            '导出', 'export',
            '总结', 'summary', 'summarize',
            '综合', 'comprehensive',
            '整合', 'integrate'
        ]
    }
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.confidence_threshold = 0.7
        self.max_retry_count = 3
    
    def _keyword_based_intent(self, user_question: str) -> Optional[Tuple[str, float]]:
        """基于关键词进行快速意图识别"""
        question_lower = user_question.lower()
        
        intent_scores = {intent: 0.0 for intent in self.VALID_INTENTS}
        
        for intent, keywords in self.KEYWORD_MAPS.items():
            for keyword in keywords:
                if keyword.lower() in question_lower:
                    intent_scores[intent] += 1.0
        
        # 找出得分最高的意图
        max_score = max(intent_scores.values())
        if max_score > 0:
            best_intent = max(intent_scores, key=intent_scores.get)
            confidence = min(max_score / 3.0, 1.0)
            return best_intent, confidence
        
        return None
    
    def _validate_intent(self, intent_type: str, confidence: float, user_question: str) -> Tuple[str, float, bool]:
        """验证意图识别结果"""
        is_valid = True
        
        # 检查意图类型是否有效
        if intent_type not in self.VALID_INTENTS:
            is_valid = False
            intent_type = 'ASK_DATA'
            confidence = 0.5
        
        # 检查置信度
        if confidence < 0.3:
            is_valid = False
            # 使用关键词识别作为备选
            keyword_result = self._keyword_based_intent(user_question)
            if keyword_result:
                intent_type, confidence = keyword_result
        
        return intent_type, confidence, is_valid
    
    def _parse_intent_json(self, content: str, user_question: str, retry_cnt: int = 0) -> Tuple[str, float, str]:
        """解析意图识别结果，带有容错和重试机制"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                intent_type = result.get('intent_type', 'ASK_DATA')
                confidence = result.get('confidence', 0.5)
                reasoning = result.get('reasoning', '')
                
                # 验证结果
                intent_type, confidence, is_valid = self._validate_intent(
                    intent_type, confidence, user_question
                )
                
                if is_valid:
                    return intent_type, confidence, reasoning
                
        except Exception as e:
            logger.warning(f"Failed to parse intent JSON: {e}")
        
        # 如果JSON解析失败，尝试关键词识别
        keyword_result = self._keyword_based_intent(user_question)
        if keyword_result:
            intent_type, confidence = keyword_result
            return intent_type, confidence, "Keyword-based intent recognition"
        
        # 最后尝试基于内容的启发式判断
        return self._heuristic_intent_detection(user_question)
    
    def _heuristic_intent_detection(self, user_question: str) -> Tuple[str, float, str]:
        """启发式意图检测"""
        question_lower = user_question.lower()
        
        # 检查是否是闲聊
        if len(user_question.strip()) < 15 and any(
            word in question_lower for word in ['你好', 'hello', 'hi', '谢谢', 'thank', '再见', 'bye']
        ):
            return 'SMALLTALK', 0.8, 'Short greeting/small talk detected'
        
        # 检查是否有可视化关键词
        if any(word in question_lower for word in ['图', 'chart', 'visualiz', 'plot']):
            return 'VISUALIZATION', 0.7, 'Visualization keywords detected'
        
        # 检查是否有分析关键词
        if any(word in question_lower for word in ['分析', 'analysis', 'predict', 'forecast', 'correl']):
            return 'ANALYSIS_MODELING', 0.7, 'Analysis keywords detected'
        
        # 检查是否有报告关键词
        if any(word in question_lower for word in ['报告', 'report', 'summary', 'export']):
            return 'REPORT', 0.7, 'Report keywords detected'
        
        # 默认ASK_DATA
        return 'ASK_DATA', 0.6, 'Default to data query intent'
    
    async def _get_intent_with_verification(
        self, 
        llm, 
        messages, 
        state, 
        retry_cnt, 
        config, 
        origin_user_question
    ):
        """获取意图并进行验证"""
        result = await astream(llm, messages, {"thinking": {"type": "enabled"}}, config)
        intent_content = result.content.strip()
        logger.info(f"Intent recognition content: {intent_content}")
        
        intent_type, confidence, reasoning = self._parse_intent_json(
            intent_content, origin_user_question, retry_cnt
        )
        
        # 检查置信度，如果过低则重试
        if confidence < self.confidence_threshold and retry_cnt < self.max_retry_count:
            logger.info(f"Confidence {confidence:.2f} below threshold, retrying...")
            retry_cnt += 1
            retry_message = {
                "role": "user",
                "content": f"""Please re-analyze the user question more carefully. Consider:
1. The primary action the user wants to perform
2. Key keywords in the question
3. Context from the conversation

User question: {origin_user_question}

Respond with valid JSON format only."""
            }
            messages.append(retry_message)
            return await self._get_intent_with_verification(
                llm, messages, state, retry_cnt, config, origin_user_question
            )
        
        messages.append({"role": "assistant", "content": intent_content})
        return intent_type, confidence, reasoning, intent_content
    
    async def run(self, state: PlanState, config: RunnableConfig):
        with tag_scope(config, MessageTag.THINK):
            llm = get_llm_by_name(self.agent_name)
            user_question = state['user_question']
            rewrite_question = user_question
            history = state.get("history") or []
            
            origin_user_question = state.get("origin_user_question", user_question)
            
            # 问题重写（如有历史对话）
            if len(history) > 0:
                rewrite_prompt = f"""
## User Question to be Rewritten
{user_question}

## Rewritten Question
        """
                input_ = {
                    "messages": history + [{"role": "user", "content": rewrite_prompt}],
                    "locale": state.get("locale")
                }
                messages = apply_prompt_template("rewrite_question", input_)
                result = await astream(llm, messages, {"thinking": {"type": "enabled"}}, config)
                rewrite_question = result.content.strip()
                logger.info(f"Question rewritten to: {rewrite_question}")
            
            # 构建意图识别消息
            intent_messages = history + [
                {"role": "user", "content": f"Determine Intent. The user question: {rewrite_question}"}
            ]
            logger.info(f"Intent recognition messages: {intent_messages}")
            
            input_ = {
                "messages": intent_messages,
                "locale": state.get("locale")
            }
            
            messages = apply_prompt_template(self.agent_name, input_)
            intent_type, confidence, reasoning, full_intent = await self._get_intent_with_verification(
                llm, messages, state, 0, config, origin_user_question
            )
            
            # 记录意图识别结果
            intent_info = {
                "step_name": "意图识别",
                "tool_used": "intent_recognition_agent",
                "execution_status": "success",
                "result": {
                    "intent_type": intent_type,
                    "confidence": confidence,
                    "reasoning": reasoning
                }
            }
            logger.info(f"Intent recognition result: {json.dumps(intent_info, ensure_ascii=False)}")
            
            # 决定路由
            goto = "plan_agent"
            if intent_type == "SMALLTALK":
                goto = "small_talk_agent"
            elif intent_type == "REPORT":
                goto = "report_workflow_router"
            
        return Command(
            update={
                "intent": full_intent,
                "intent_type": intent_type,
                "intent_confidence": confidence,
                "user_question": rewrite_question,
                "origin_user_question": user_question,
                "materials": []
            },
            goto=goto
        )
