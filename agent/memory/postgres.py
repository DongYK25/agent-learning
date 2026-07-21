"""PostgreSQL 版 Memory：sessions + messages 持久化。"""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agent import config


def _assistant_payload(message: Any) -> dict[str, Any]:
    """把 assistant 消息（dict / SDK 对象）规范成可入库 dict。"""
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
    payload.setdefault("role", "assistant")
    return payload


def _to_jsonable(value: Any) -> Any:
    """确保 tool_calls 等可写入 JSONB。"""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _row_to_message(row: dict[str, Any]) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": row["role"], "content": row["content"]}
    if row.get("tool_call_id"):
        msg["tool_call_id"] = row["tool_call_id"]
    if row.get("tool_calls") is not None:
        msg["tool_calls"] = row["tool_calls"]
    if row.get("name"):
        msg["name"] = row["name"]
    return msg


class PgMemory:
    """PostgreSQL Memory，API 与内存版 Memory 对齐。"""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or config.DATABASE_URL
        self._conn = psycopg.connect(self._dsn, row_factory=dict_row)

    def close(self) -> None:
        self._conn.close()

    def ensure_session(
        self,
        session_id: str,
        *,
        prompt_name: str | None = None,
        model: str | None = None,
    ) -> None:
        """确保 sessions 行存在；传入 prompt_name/model 时会更新元数据。"""
        with self._conn.cursor() as cur:
            if prompt_name is None and model is None:
                cur.execute(
                    """
                    INSERT INTO sessions (id)
                    VALUES (%s::uuid)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (session_id,),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO sessions (id, prompt_name, model)
                    VALUES (%s::uuid, COALESCE(%s, 'assistant'), %s)
                    ON CONFLICT (id) DO UPDATE SET
                        updated_at = now(),
                        prompt_name = COALESCE(EXCLUDED.prompt_name, sessions.prompt_name),
                        model = COALESCE(EXCLUDED.model, sessions.model)
                    """,
                    (session_id, prompt_name, model),
                )
        self._conn.commit()

    def load(self, session_id: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, tool_call_id, tool_calls, name
                FROM messages
                WHERE session_id = %s::uuid
                ORDER BY position
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        return [_row_to_message(row) for row in rows]

    def save(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self.ensure_session(session_id)
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM messages WHERE session_id = %s::uuid",
                (session_id,),
            )
            for i, msg in enumerate(messages):
                cur.execute(
                    """
                    INSERT INTO messages (
                        session_id, position, role, content,
                        tool_call_id, tool_calls, name, raw
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        session_id,
                        i,
                        msg.get("role"),
                        msg.get("content"),
                        msg.get("tool_call_id"),
                        Jsonb(_to_jsonable(msg["tool_calls"]))
                        if "tool_calls" in msg and msg["tool_calls"] is not None
                        else None,
                        msg.get("name"),
                        Jsonb(_to_jsonable(msg)),
                    ),
                )
            cur.execute(
                "UPDATE sessions SET updated_at = now() WHERE id = %s::uuid",
                (session_id,),
            )
        self._conn.commit()

    def add_system(self, session_id: str, content: str) -> None:
        self._append(session_id, {"role": "system", "content": content})

    def add_user(self, session_id: str, content: str) -> None:
        self._append(session_id, {"role": "user", "content": content})

    def add_assistant(self, session_id: str, message: Any) -> None:
        self._append(session_id, _assistant_payload(message))

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
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM messages
                WHERE id = (
                    SELECT id FROM messages
                    WHERE session_id = %s::uuid
                    ORDER BY position DESC
                    LIMIT 1
                )
                RETURNING role, content, tool_call_id, tool_calls, name
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE sessions SET updated_at = now() WHERE id = %s::uuid",
                    (session_id,),
                )
        self._conn.commit()
        return _row_to_message(row) if row else None

    def _append(self, session_id: str, message: dict[str, Any]) -> None:
        self.ensure_session(session_id)
        tool_calls = message.get("tool_calls")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (
                    session_id, position, role, content,
                    tool_call_id, tool_calls, name, raw
                )
                VALUES (
                    %s::uuid,
                    COALESCE(
                        (SELECT MAX(position) FROM messages WHERE session_id = %s::uuid),
                        -1
                    ) + 1,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    session_id,
                    session_id,
                    message.get("role"),
                    message.get("content"),
                    message.get("tool_call_id"),
                    Jsonb(_to_jsonable(tool_calls)) if tool_calls is not None else None,
                    message.get("name"),
                    Jsonb(_to_jsonable(message)),
                ),
            )
            cur.execute(
                "UPDATE sessions SET updated_at = now() WHERE id = %s::uuid",
                (session_id,),
            )
        self._conn.commit()
