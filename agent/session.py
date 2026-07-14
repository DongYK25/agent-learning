"""Session：绑定 session_id、memory、setting。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent.memory import Memory


@dataclass
class SessionSetting:
    prompt_name: str = "assistant"
    model: str | None = None


@dataclass
class Session:
    memory: Memory
    setting: SessionSetting = field(default_factory=SessionSetting)
    session_id: str = field(default_factory=lambda: str(uuid4()))

    def load(self) -> list[dict[str, Any]]:
        return self.memory.load(self.session_id)

    def add_system(self, content: str) -> None:
        self.memory.add_system(self.session_id, content)

    def add_user(self, content: str) -> None:
        self.memory.add_user(self.session_id, content)

    def add_assistant(self, message: Any) -> None:
        self.memory.add_assistant(self.session_id, message)

    def add_tool(self, tool_call_id: str, content: str) -> None:
        self.memory.add_tool(self.session_id, tool_call_id, content)

    def pop_last(self) -> dict[str, Any] | None:
        return self.memory.pop_last(self.session_id)
