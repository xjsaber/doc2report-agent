"""OpenAI-compatible chat client; keys come only from environment / .env."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class ChatModel(Protocol):
    def complete(self, messages: Sequence[ChatMessage]) -> str:
        """Return assistant text for the given chat messages."""
        ...


class FakeChatModel:
    """Deterministic stand-in for tests; never calls a network."""

    def __init__(
        self,
        reply: str | Sequence[str] = "这是基于检索片段的回答。",
        *,
        reply_factory=None,
    ) -> None:
        if isinstance(reply, str):
            self._replies = [reply]
        else:
            self._replies = list(reply)
        self.reply_factory = reply_factory
        self.calls: list[list[ChatMessage]] = []
        self._index = 0

    @property
    def reply(self) -> str:
        return self._replies[min(self._index, len(self._replies) - 1)]

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if self.reply_factory is not None:
            out = self.reply_factory(messages, self._index)
            self._index += 1
            return out
        out = self._replies[min(self._index, len(self._replies) - 1)]
        self._index += 1
        return out


class OpenAICompatibleChat:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("API_KEY is required for OpenAICompatibleChat")
        self.api_key = api_key.strip()
        self.base_url = (base_url or os.getenv("BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.getenv("MODEL") or "deepseek-flash"

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError('Install the qa extra: pip install -e ".[qa]"') from exc
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content or not str(content).strip():
            raise RuntimeError("Chat model returned an empty response")
        return str(content).strip()


def build_chat_model(*, api_key: str | None = None, base_url: str | None = None,
                     model: str | None = None) -> ChatModel | None:
    """Return a live client when API_KEY is set; otherwise None (retrieval-only)."""
    key = api_key if api_key is not None else os.getenv("API_KEY", "")
    if not key or not str(key).strip():
        return None
    return OpenAICompatibleChat(api_key=str(key), base_url=base_url, model=model)
