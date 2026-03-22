import logging
import uuid
import json
import re

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

class IntentRecognitionAgent:
    """Agent for recognizing customer intent from their questions."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def _parse_intent_json(self, content: str):
        """Parse intent recognition result from JSON format"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                intent_type = result.get('intent_type', 'ASK_DATA')
                confidence = result.get('confidence', 0.5)
                reasoning = result.get('reasoning', '')
                return intent_type, confidence, reasoning
        except Exception as e:
            logger.warning(f"Failed to parse intent JSON: {e}")
        
        if 'SMALLTALK' in content:
            return 'SMALLTALK', 0.8, 'Legacy format detected'
        elif 'ASK_DATA' in content:
            return 'ASK_DATA', 0.8, 'Legacy format detected'
        elif 'ANALYSIS_MODELING' in content:
            return 'ANALYSIS_MODELING', 0.8, 'Legacy format detected'
        elif 'VISUALIZATION' in content:
            return 'VISUALIZATION', 0.8, 'Legacy format detected'
        elif 'REPORT' in content:
            return 'REPORT', 0.8, 'Legacy format detected'
        else:
            return 'ASK_DATA', 0.5, 'Default to ASK_DATA'

    async def _get_intent(self, llm, messages, state, retry_cnt, config):
        result = await astream(llm, messages, {"thinking": {"type": "enabled"}}, config)
        intent_content = result.content.strip()
        logger.info(f"intent content: {intent_content}")
        
        intent_type, confidence, reasoning = self._parse_intent_json(intent_content)
        
        valid_intents = ['SMALLTALK', 'ASK_DATA', 'ANALYSIS_MODELING', 'VISUALIZATION', 'REPORT']
        if intent_type not in valid_intents:
            if retry_cnt < 3:
                retry_cnt = retry_cnt + 1
                # 使用state.get()避免KeyError
                user_question = state.get('origin_user_question', state.get('user_question', ''))
                messages.append({"role": "user", "content": f"Determine Intent. Just answer with valid JSON format. The valid intent types are: SMALLTALK, ASK_DATA, ANALYSIS_MODELING, VISUALIZATION, REPORT. The user question: {user_question}"})
                return await self._get_intent(llm, messages, state, retry_cnt, config)
        
        messages.append({"role": "assistant", "content": intent_content})
        return intent_type, confidence, reasoning, intent_content


    async def run(self, state: PlanState, config: RunnableConfig):
        with tag_scope(config, MessageTag.THINK):
            llm = get_llm_by_name(self.agent_name)
            user_question = state['user_question']
            rewrite_question = user_question
            history = state.get("history") or []
            
            # 设置origin_user_question，确保在重试时可用
            state["origin_user_question"] = user_question
            
            rewrite_prompt = f"""
## User Question to be Rewritten
{user_question}

## Rewritten Question
        """
            if len(history) > 0:
                input_ = {
                    "messages": history + [{"role": "user", "content": rewrite_prompt}],
                    "locale": state.get("locale")
                }
                messages = apply_prompt_template("rewrite_question", input_)
                result = await astream(llm, messages, {"thinking": {"type": "enabled"}}, config)
                rewrite_question = result.content.strip()
                logger.info(f"Question rewritten to: {rewrite_question}")

            intent_messages = history + [{"role": "user", "content": f"Determine Intent. The user question: {rewrite_question}"}]
            logger.info(f"messages: {intent_messages}")
            input_ = {
                "messages": intent_messages,
                "locale": state.get("locale")
            }

            messages = apply_prompt_template(self.agent_name, input_)
            intent_type, confidence, reasoning, full_intent = await self._get_intent(llm, messages, state, 0, config)

            goto = "plan_agent"
            if intent_type == "SMALLTALK":
                goto = "small_talk_agent"
            elif intent_type == "ASK_DATA":
                goto = "search_agent"
            elif intent_type == "ANALYSIS_MODELING":
                goto = "analysis_agent"
            elif intent_type == "VISUALIZATION":
                goto = "visualization_agent"
            elif intent_type == "REPORT":
                goto = "report_agent"
        
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