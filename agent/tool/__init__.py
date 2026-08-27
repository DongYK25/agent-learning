"""Tool 协议：schema 给模型看，Pydantic 在 execute 前再验。"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from agent.tool.result import ToolResult


class Tool(Protocol):
    name: str
    description: str
    args_model: type[BaseModel]
    idempotent: bool
    parallel_safe: bool
    timeout_seconds: float

    @property
    def schema(self) -> dict[str, Any]:
        """OpenAI function-calling 格式的 tool 定义。"""
        ...

    def execute(self, args: BaseModel) -> ToolResult: ...
