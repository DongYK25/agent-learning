"""会话记忆：Agent 只通过 Memory API 读写，不直接操作 messages。"""

from __future__ import annotations

from typing import Any


class Memory:
    """内存版 Memory。以后可换成 SQLite / PostgreSQL / Redis / Summary。"""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}

    def load(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._store.get(session_id, []))

    def save(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self._store[session_id] = list(messages)

    def add_system(self, session_id: str, content: str) -> None:
        self._append(session_id, {"role": "system", "content": content})

    def add_user(self, session_id: str, content: str) -> None:
        self._append(session_id, {"role": "user", "content": content})

    def add_assistant(self, session_id: str, message: Any) -> None:
        """追加 assistant 消息（可能含 tool_calls）。支持 dict 或 SDK 对象。"""
        if hasattr(message, "model_dump"):
            payload = message.model_dump(exclude_none=True)
        elif isinstance(message, dict):
            payload = dict(message)
        else:
            payload = {
                "role": "assistant",
                "content": getattr(message, "content", None),
            }
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                payload["tool_calls"] = tool_calls
        self._append(session_id, payload)

    def add_tool(self, session_id: str, tool_call_id: str, content: str) -> None:
        self._append(
            session_id,
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            },
        )

    def pop_last(self, session_id: str) -> dict[str, Any] | None:
        msgs = self._store.get(session_id)
        if not msgs:
            return None
        return msgs.pop()

    def _append(self, session_id: str, message: dict[str, Any]) -> None:
        self._store.setdefault(session_id, []).append(message)
