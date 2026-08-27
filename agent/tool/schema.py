"""Pydantic 模型 → OpenAI function-calling schema。一份契约两头用。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def openai_tool_schema(
    name: str,
    description: str,
    args_model: type[BaseModel],
) -> dict[str, Any]:
    params = args_model.model_json_schema()
    params.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params,
        },
    }
