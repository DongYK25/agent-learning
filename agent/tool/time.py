"""当前时间 Tool。无外网，只为证明加 Tool 不用改 Agent 循环。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.tool.result import ToolResult
from agent.tool.schema import openai_tool_schema


class TimeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timezone: str = Field(
        default="Asia/Shanghai",
        max_length=64,
        description="IANA 时区名，例如 Asia/Shanghai、UTC。默认 Asia/Shanghai。",
    )

    @field_validator("timezone", mode="before")
    @classmethod
    def strip_timezone(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or "Asia/Shanghai"
        return value

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"未知时区: {value}") from e
        return value


class TimeTool:
    name = "get_current_time"
    description = "查询当前日期和时间。用户问几点、现在时间、今天日期时使用。"
    args_model = TimeArgs
    idempotent = True
    parallel_safe = True
    timeout_seconds = 5.0

    @property
    def schema(self) -> dict[str, Any]:
        return openai_tool_schema(self.name, self.description, self.args_model)

    def execute(self, args: TimeArgs) -> ToolResult:
        now = datetime.now(ZoneInfo(args.timezone))
        return ToolResult.success(
            {
                "timezone": args.timezone,
                "datetime": now.isoformat(timespec="seconds"),
            }
        )
