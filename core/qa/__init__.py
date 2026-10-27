"""Standalone RAG Q&A helpers (no report graph dependency)."""

from core.qa.answer import AnswerResult, Citation, answer_question, load_dotenv_config
from core.qa.llm import ChatMessage, FakeChatModel, OpenAICompatibleChat, build_chat_model

__all__ = [
    "AnswerResult",
    "Citation",
    "ChatMessage",
    "FakeChatModel",
    "OpenAICompatibleChat",
    "answer_question",
    "build_chat_model",
    "load_dotenv_config",
]
