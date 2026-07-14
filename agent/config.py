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


def require_api_key() -> str:
    if not DEEPSEEK_API_KEY:
        print("请先在 .env 中设置 DEEPSEEK_API_KEY（可参考 .env.example）")
        sys.exit(1)
    return DEEPSEEK_API_KEY
