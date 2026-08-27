"""统一 Tool 执行结果。写入 Memory 的仍是 JSON 字符串。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

ToolStatus = Literal[
    "ok",
    "validation_error",
    "timeout",
    "upstream_error",
    "unknown_tool",
    "invalid_json",
    "execute_failed",
]


@dataclass
class ToolResult:
    ok: bool
    status: ToolStatus
    data: Any = None
    error: str | None = None
    truncated: bool = False

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "status": self.status,
            "truncated": self.truncated,
        }
        if self.data is not None:
            payload["data"] = self.data
        if not self.ok:
            payload["error"] = self.error
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def success(cls, data: Any) -> ToolResult:
        return cls(ok=True, status="ok", data=data)

    @classmethod
    def fail(cls, status: ToolStatus, error: str) -> ToolResult:
        return cls(ok=False, status=status, error=error)
