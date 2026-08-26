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
        """执行工具。任何失败都返回 JSON error 字符串，不向循环抛异常。"""
        try:
            tool = self._tools.get(name)
            if tool is None:
                return _error("unknown_tool", f"未知工具: {name}")
            try:
                args = json.loads(arguments_json or "{}")
            except json.JSONDecodeError as e:
                return _error("invalid_json", str(e))
            if not isinstance(args, dict):
                return _error("invalid_args", "参数必须是 JSON 对象")
            return tool.execute(**args)
        except Exception as e:
            return _error("execute_failed", str(e))


def _error(code: str, message: str) -> str:
    return json.dumps({"error": code, "message": message}, ensure_ascii=False)


def build_default_registry() -> ToolRegistry:
    from agent.tool.weather import WeatherTool

    registry = ToolRegistry()
    registry.register(WeatherTool())
    return registry
