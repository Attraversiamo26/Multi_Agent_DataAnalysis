import json
import logging
import uuid
import os
import datetime
from pathlib import Path
from typing import List, Dict, Optional

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import push_message
from langgraph.types import Command

from src.entity.states import PlanState
from src.llms.llm import get_llm_by_name
from src.utils.llm_utils import astream

logger = logging.getLogger(__name__)


class GenerateAgent:
    """Agent responsible for generating reflection texts based on reference document content."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.reference_doc_path = os.path.join(os.getcwd(), ".trae", "documents", "data_analysis_enhancement_plan.md")

    def _load_reference_document(self) -> str:
        """Load the reference document content."""
        try:
            if os.path.exists(self.reference_doc_path):
                with open(self.reference_doc_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"Error loading reference document: {str(e)}")
        return ""

    def _save_generated_content(self, content: str, topic: str) -> str:
        """Save generated reflection text."""
        output_dir = os.path.join(os.getcwd(), "generated_reflections")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')[:20]
        filename = f"reflection_{safe_topic}_{timestamp}.txt"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        return filepath

    async def run(self, state: PlanState, config: RunnableConfig):
        push_message(HumanMessage(
            content="Generating reflection text",
            id=f"record-{uuid.uuid4()}"
        ))

        messages = state.get("history") or []
        user_question = state.get('user_question', '')

        params = {
            "topic": "",
            "word_limit": 500,
            "outline": []
        }

        import re
        
        topic_match = re.search(r'关于([^，,]+)的心得体会', user_question)
        if topic_match:
            params["topic"] = topic_match.group(1)
        
        word_limit_match = re.search(r'字数限制(\d+)字', user_question)
        if word_limit_match:
            params["word_limit"] = int(word_limit_match.group(1))
        
        outline_match = re.search(r'提纲包括[：:]\s*(.+?)(?=\s*$|\s*，|\s*。)', user_question)
        if outline_match:
            outline_text = outline_match.group(1)
            params["outline"] = [item.strip() for item in re.split(r'[1234567890、.\n]+', outline_text) if item.strip()]

        if not params["topic"]:
            topic_match = re.search(r'生成(.+?)心得体会', user_question)
            if topic_match:
                params["topic"] = topic_match.group(1).strip()

        reference_content = self._load_reference_document()

        system_prompt = """你是一个专业的心得体会写作助手。请根据用户提供的主题、字数限制和大纲，生成一篇高质量的心得体会。

写作要求：
1. 内容要真实、深刻，有个人感悟
2. 语言表达流畅自然
3. 结构清晰，逻辑连贯
4. 结合参考文档的主题和内容（如果相关）
5. 字数严格控制在要求范围内

参考历史文档内容
"""

        if reference_content:
            system_prompt += f"\n{reference_content[:3000]}\n"

        system_prompt += """
请确保生成的心得体会：
- 有明确的开头、正文和结尾
- 包含具体的例子或感受
- 语言积极向上，充满正能量
- 符合中文表达习惯
"""

        outline_text = "\n".join([f"- {item}" for item in params["outline"]]) if params["outline"] else "没有提供具体大纲，可自由发挥"

        user_prompt = f"""请生成一篇心得体会，参数如下：

主题：{params["topic"] or '请围绕数据分析相关主题生成心得体会'}
字数限制：{params["word_limit"]}字左右
大纲：
{outline_text}

请直接开始生成心得体会内容。"""

        generation_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        logger.info(f"Generating reflection with parameters: {params}")

        llm = get_llm_by_name(self.agent_name)
        result = await astream(llm, generation_messages, {"thinking": {"type": "enabled"}}, config)
        response_content = result.content

        topic_for_file = params["topic"] if params["topic"] else "general"
        export_path = self._save_generated_content(response_content, topic_for_file)
        logger.info(f"Reflection exported to: {export_path}")

        final_content = f"{response_content}\n\n---\n📄 已保存到: {export_path}"

        messages.append({"role": "assistant", "content": final_content})
        logger.info(f"Reflection generated successfully")

        return Command(
            update={"reflection_export_path": export_path},
            goto="__end__",
        )