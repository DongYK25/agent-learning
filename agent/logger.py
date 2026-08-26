"""结构化 Agent 日志，方便 Debug。"""

from __future__ import annotations

import logging
from typing import Any

from agent import config

_SEP = "-" * 16


def setup_logging() -> logging.Logger:
    """Agent 日志只写文件，避免和终端 print 重复。"""
    logger = logging.getLogger("agent")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(file_handler)

    # 第三方库的 HTTP 请求日志也不刷屏到终端
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    return logger


class AgentLogger:
    """按 USER / LLM / Tool 分段记录，便于排查。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or setup_logging()

    def user(self, content: str) -> None:
        self._log.info("\n[USER]\n%s\n%s", content, _SEP)

    def llm_tool_calls(self, tool_calls: list[Any]) -> None:
        names = []
        for tc in tool_calls:
            name = getattr(getattr(tc, "function", None), "name", None)
            if name is None and isinstance(tc, dict):
                name = tc.get("function", {}).get("name")
            names.append(name or "?")
        self._log.info("\n[LLM]\nTool:\n%s\n%s", "\n".join(names), _SEP)

    def llm_reply(self, content: str | None) -> None:
        self._log.info("\n[LLM]\n%s\n%s", content or "(空)", _SEP)

    def tool(self, name: str, arguments: str, result: str) -> None:
        self._log.info(
            "\n[Tool]\n%s\n%s\n↓\n%s\n%s",
            name,
            arguments,
            result,
            _SEP,
        )

    def loop_step(self, step: int, max_steps: int, status: str) -> None:
        self._log.info(
            "\n[LOOP]\nstep=%s/%s status=%s\n%s",
            step,
            max_steps,
            status,
            _SEP,
        )

    def loop_stop(
        self,
        step: int,
        max_steps: int,
        reason: str,
        detail: str | None = None,
    ) -> None:
        extra = f"\n{detail}" if detail else ""
        self._log.info(
            "\n[LOOP]\nstop step=%s/%s reason=%s%s\n%s",
            step,
            max_steps,
            reason,
            extra,
            _SEP,
        )
