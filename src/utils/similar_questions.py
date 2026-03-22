import json
import logging
from typing import List, Dict, Any

from src.llms.llm import get_llm_by_name
from src.utils.llm_utils import astream

logger = logging.getLogger(__name__)


class SimilarQuestionsGenerator:
    """Generate similar questions based on user input and context"""

    def __init__(self):
        self.llm = get_llm_by_name("extract")

    async def generate_similar_questions(
        self, 
        user_question: str, 
        context: List[Dict[str, str]] = None
    ) -> List[str]:
        """
        Generate similar questions based on the user's current question and context

        Args:
            user_question: The user's current question
            context: Optional list of previous messages for context

        Returns:
            List of similar questions
        """
        try:
            # Build context string
            context_str = ""
            if context:
                for msg in context[-5:]:  # Limit to last 5 messages for context
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        context_str += f"{role}: {content}\n"

            # Create prompt for generating similar questions
            input_ = {
                "messages": [{
                    "role": "user", 
                    "content": f"""
Based on the following user question and conversation context, generate 3-5 similar questions that the user might want to ask next:

### Current Question
{user_question}

### Conversation Context
{context_str}

### Requirements
- Generate questions that are relevant to the current topic
- Questions should be specific and actionable
- Vary the angle and depth of the questions
- Focus on common follow-up questions users might have
- Return only the questions, one per line, without any additional text
"""
                }],
                "locale": "zh-CN"
            }

            # Create messages directly (no template needed - we built the prompt already)
            messages = input_["messages"]

            # Generate similar questions
            result = await astream(
                self.llm, 
                messages, 
                {"thinking": {"type": "disabled"}}
            )

            response_content = result.content
            logger.info(f"Similar questions generation response: {response_content}")

            # Parse the generated questions
            questions = []
            for line in response_content.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Remove numbering if present
                    if line[0].isdigit():
                        line = line.split('.', 1)[1].strip()
                    questions.append(line)

            # Limit to maximum 5 questions
            return questions[:5]

        except Exception as e:
            logger.error(f"Error generating similar questions: {str(e)}")
            return []


async def get_similar_questions(
    user_question: str, 
    context: List[Dict[str, str]] = None
) -> List[str]:
    """
    Helper function to get similar questions

    Args:
        user_question: The user's current question
        context: Optional list of previous messages for context

    Returns:
        List of similar questions
    """
    generator = SimilarQuestionsGenerator()
    return await generator.generate_similar_questions(user_question, context)
