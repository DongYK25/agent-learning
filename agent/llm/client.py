"""DeepSeek / OpenAI 兼容客户端。"""

from __future__ import annotations

from openai import OpenAI

from agent import config


def create_client() -> OpenAI:
    return OpenAI(
        api_key=config.require_api_key(),
        base_url=config.DEEPSEEK_BASE_URL,
    )


class LLMClient:
    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        self.client = client or create_client()
        self.model = model or config.DEEPSEEK_MODEL

    def chat(self, messages: list, tools: list | None = None):
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return self.client.chat.completions.create(
            timeout=config.LLM_TIMEOUT_SECONDS,
            **kwargs,
        )
