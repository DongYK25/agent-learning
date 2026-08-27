"""天气 Tool。只请求配置里的 WEATHER_API_URL（隐式 URL 白名单，沙箱概念）。"""

from __future__ import annotations

from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent import config
from agent.tool.result import ToolResult
from agent.tool.schema import openai_tool_schema


class WeatherArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="城市名，例如：北京、上海、杭州。不能为空，最多 32 个字符。",
    )

    @field_validator("city", mode="before")
    @classmethod
    def strip_city(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class WeatherTool:
    name = "get_weather"
    description = "查询指定城市的实时天气。用户问到天气、气温、是否下雨等时使用。"
    args_model = WeatherArgs
    idempotent = True
    parallel_safe = True

    @property
    def timeout_seconds(self) -> float:
        return float(config.TOOL_TIMEOUT_SECONDS)

    @property
    def schema(self) -> dict[str, Any]:
        return openai_tool_schema(self.name, self.description, self.args_model)

    def execute(self, args: WeatherArgs) -> ToolResult:
        try:
            resp = requests.get(
                config.WEATHER_API_URL,
                params={"city": args.city},
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError:
                data = {"text": resp.text}
            return ToolResult.success(data)
        except requests.Timeout as e:
            return ToolResult.fail("timeout", str(e))
        except requests.RequestException as e:
            return ToolResult.fail("upstream_error", str(e))
