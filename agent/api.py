"""HTTP 服务（v0.5）：无状态请求 + PostgreSQL 有状态会话。

已知缺口（本版不做）：
- 同步阻塞：一次 Agent 循环可能多次调 LLM/Tool，客户端/代理可能先超时。v0.6 用流式解决体感。
- 无鉴权：知道 session_id 就能读写该会话。v1.0 再加 Key。
- 无流式：等整段结束后才返回。
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import config
from agent.llm import LLMClient
from agent.logger import AgentLogger
from agent.main import LoopAborted, run_user_turn
from agent.memory import PgMemory
from agent.prompt import load_prompt
from agent.session import Session, SessionSetting
from agent.tool.registry import build_default_registry

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_session_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(session_id: str) -> threading.Lock:
    with _locks_guard:
        return _session_locks.setdefault(session_id, threading.Lock())


class AppState:
    memory: PgMemory
    llm: LLMClient
    registry: Any
    agent_log: AgentLogger


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    state.memory = PgMemory()
    state.llm = LLMClient()
    state.registry = build_default_registry()
    state.agent_log = AgentLogger()
    app.state.rt = state
    yield
    state.memory.close()


app = FastAPI(
    title="agent-learning",
    version="0.5",
    description="Session 级多租户：客户端持有 session_id，历史在 PostgreSQL。",
    lifespan=lifespan,
)


class CreateSessionBody(BaseModel):
    prompt_name: str | None = None


class PostMessageBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)


class SessionCreated(BaseModel):
    session_id: str
    prompt_name: str


class MessageReply(BaseModel):
    session_id: str
    reply: str


class HistoryBody(BaseModel):
    session_id: str
    prompt_name: str | None = None
    model: str | None = None
    messages: list[dict[str, Any]]


def _runtime(app: FastAPI) -> AppState:
    return app.state.rt


def _open_session(memory: PgMemory, session_id: str) -> Session:
    meta = memory.get_session(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    return Session(
        memory=memory,
        setting=SessionSetting(
            prompt_name=meta.get("prompt_name") or config.DEFAULT_PROMPT,
            model=meta.get("model"),
        ),
        session_id=session_id,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/sessions", status_code=201)
def create_session(body: CreateSessionBody | None = None) -> SessionCreated:
    rt = _runtime(app)
    prompt_name = (body.prompt_name if body else None) or config.DEFAULT_PROMPT
    try:
        system = load_prompt(prompt_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    session = Session(
        memory=rt.memory,
        setting=SessionSetting(prompt_name=prompt_name),
    )
    rt.memory.ensure_session(
        session.session_id,
        prompt_name=prompt_name,
        model=session.setting.model,
    )
    session.add_system(system)
    return SessionCreated(session_id=session.session_id, prompt_name=prompt_name)


@app.get("/sessions/{session_id}")
def get_session(session_id: UUID) -> HistoryBody:
    rt = _runtime(app)
    sid = str(session_id)
    meta = rt.memory.get_session(sid)
    if meta is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    return HistoryBody(
        session_id=sid,
        prompt_name=meta.get("prompt_name"),
        model=meta.get("model"),
        messages=rt.memory.load(sid),
    )


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: UUID) -> HistoryBody:
    return get_session(session_id)


@app.post("/sessions/{session_id}/messages")
def post_message(session_id: UUID, body: PostMessageBody) -> MessageReply:
    rt = _runtime(app)
    sid = str(session_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")

    with _lock_for(sid):
        session = _open_session(rt.memory, sid)
        try:
            reply = run_user_turn(
                session,
                rt.llm,
                rt.registry,
                rt.agent_log,
                content,
                echo=False,
            )
        except LoopAborted as e:
            raise HTTPException(
                status_code=502,
                detail=f"模型服务暂时不可用: {e}",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    return MessageReply(session_id=sid, reply=reply)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "agent.api:app",
        host=config.HTTP_HOST,
        port=config.HTTP_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
