"""从环境变量加载配置。"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://localhost:8091/weather")
DEFAULT_PROMPT = os.getenv("DEFAULT_PROMPT", "assistant")
LOG_FILE = os.getenv("AGENT_LOG_FILE", "agent.log")

# PostgreSQL：默认 127.0.0.1:5432/server
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/server",
)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


# v0.3 循环护栏：单次用户消息内的 LLM 调用上限；连续 Tool 失败次数上限。
MAX_STEPS = max(1, _int_env("AGENT_MAX_STEPS", 8))
MAX_CONSECUTIVE_TOOL_ERRORS = max(1, _int_env("AGENT_MAX_CONSECUTIVE_TOOL_ERRORS", 3))
LLM_TIMEOUT_SECONDS = max(1, _int_env("AGENT_LLM_TIMEOUT_SECONDS", 60))
# 天气 GET 幂等，允许有限次重试（总尝试次数，含第一次）。
TOOL_MAX_ATTEMPTS = max(1, _int_env("AGENT_TOOL_MAX_ATTEMPTS", 2))


def require_api_key() -> str:
    if not DEEPSEEK_API_KEY:
        print("请先在 .env 中设置 DEEPSEEK_API_KEY（可参考 .env.example）")
        sys.exit(1)
    return DEEPSEEK_API_KEY
