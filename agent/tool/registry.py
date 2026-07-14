"""Tool 注册表：自动汇总 schemas 与执行入口。"""

from __future__ import annotations

import json
from typing import Any

from agent.tool import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema for t in self._tools.values()]

    def execute(self, name: str, arguments_json: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
        args = json.loads(arguments_json or "{}")
        return tool.execute(**args)


def build_default_registry() -> ToolRegistry:
    from agent.tool.weather import WeatherTool

    registry = ToolRegistry()
    registry.register(WeatherTool())
    return registry
