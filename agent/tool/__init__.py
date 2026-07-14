"""Tool 基类与协议。"""

from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def schema(self) -> dict[str, Any]:
        """OpenAI function-calling 格式的 tool 定义。"""
        ...

    def execute(self, **kwargs: Any) -> str: ...
