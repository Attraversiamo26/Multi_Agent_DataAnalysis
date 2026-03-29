import logging

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.entity.states import PlanState
from src.llms.llm import get_llm_by_name
from src.prompts.template import apply_prompt_template
from src.utils.llm_utils import astream

logger = logging.getLogger(__name__)
class SmallTalkAgent:
    """Agent responsible for casual conversation."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    async def run(self, state: PlanState, config: RunnableConfig):
        llm = get_llm_by_name(self.agent_name)
        history = state.get("history", [])
        
        # 确保 history 不为空，如果为空则添加默认的用户消息
        if not history:
            user_question = state.get("user_question", "你好")
            history = [{"role": "user", "content": user_question}]
        
        input_ = {
            "messages": history,
            "locale": state.get("locale")
        }

        messages = apply_prompt_template(self.agent_name, input_)
        result = await astream(llm, messages, {"temperature": 1}, config)
        
        logger.info(f"content: {result.content}")

        return Command(
            update={
                "history": state.get("history", []) + [{"role": "assistant", "content": result.content}]
            },
            goto="__end__",
        )
