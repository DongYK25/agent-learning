"""Tool 注册表：校验、幂等重试、截断、并行只读调用。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pydantic import ValidationError

from agent import config
from agent.tool import Tool
from agent.tool.result import ToolResult

_RETRYABLE = {"timeout", "upstream_error"}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema for t in self._tools.values()]

    def execute(self, name: str, arguments_json: str) -> str:
        """执行单个工具。任何失败都返回 ToolResult JSON，不向循环抛异常。"""
        try:
            result = self._execute_one(name, arguments_json)
        except Exception as e:
            result = ToolResult.fail("execute_failed", str(e))
        return _truncate(result).to_json()

    def execute_many(self, calls: list[tuple[str, str]]) -> list[str]:
        """按原始顺序返回结果。

        一轮多个 tool_calls：
        - 全部 parallel_safe（只读、无互相依赖）→ 并发
        - 任一写操作 / 有先后依赖 → 整批串行
        未知工具不阻断并发（只返回 unknown_tool）。
        """
        if not calls:
            return []
        if len(calls) == 1 or not self._all_parallel_safe(calls):
            return [self.execute(name, args) for name, args in calls]

        results: list[str] = [""] * len(calls)
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = {
                pool.submit(self.execute, name, args): i
                for i, (name, args) in enumerate(calls)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except Exception as e:
                    results[i] = ToolResult.fail("execute_failed", str(e)).to_json()
        return results

    def _all_parallel_safe(self, calls: list[tuple[str, str]]) -> bool:
        for name, _ in calls:
            tool = self._tools.get(name)
            if tool is not None and not tool.parallel_safe:
                return False
        return True

    def _execute_one(self, name: str, arguments_json: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.fail("unknown_tool", f"未知工具: {name}")
        try:
            raw_args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as e:
            return ToolResult.fail("invalid_json", str(e))
        if not isinstance(raw_args, dict):
            return ToolResult.fail("invalid_json", "参数必须是 JSON 对象")

        try:
            args = tool.args_model.model_validate(raw_args)
        except ValidationError as e:
            return ToolResult.fail("validation_error", _format_validation(e))

        attempts = config.TOOL_MAX_ATTEMPTS if tool.idempotent else 1
        last = ToolResult.fail("execute_failed", "未执行")
        for _ in range(attempts):
            last = _call_tool(tool, args)
            if last.ok or last.status not in _RETRYABLE:
                break
        return last


def _call_tool(tool: Tool, args: Any) -> ToolResult:
    try:
        result = tool.execute(args)
        if isinstance(result, ToolResult):
            return result
        return ToolResult.success(result)
    except TimeoutError as e:
        return ToolResult.fail("timeout", str(e))
    except Exception as e:
        return ToolResult.fail("execute_failed", str(e))


def _format_validation(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "参数校验失败"


def _truncate(result: ToolResult) -> ToolResult:
    max_chars = config.TOOL_RESULT_MAX_CHARS
    if len(result.to_json()) <= max_chars:
        return result
    result.truncated = True
    budget = max(64, max_chars - 160)
    if result.data is not None:
        data_s = (
            result.data
            if isinstance(result.data, str)
            else json.dumps(result.data, ensure_ascii=False)
        )
        result.data = data_s[:budget] + "…(truncated)"
    elif result.error:
        result.error = result.error[:budget] + "…(truncated)"
    return result


def build_default_registry() -> ToolRegistry:
    from agent.tool.time import TimeTool
    from agent.tool.weather import WeatherTool

    registry = ToolRegistry()
    registry.register(WeatherTool())
    registry.register(TimeTool())
    return registry
