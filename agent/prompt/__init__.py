"""从 prompt/ 目录加载系统提示词。"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent


def load_prompt(name: str = "assistant") -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"找不到 prompt 文件: {path}")
    return path.read_text(encoding="utf-8").strip()
