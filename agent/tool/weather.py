"""天气 Tool。"""

from __future__ import annotations

import json
from typing import Any

import requests

from agent import config


class WeatherTool:
    name = "get_weather"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "查询指定城市的实时天气。用户问到天气、气温、是否下雨等时使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名，例如：北京、上海、杭州",
                        }
                    },
                    "required": ["city"],
                },
            },
        }

    def execute(self, city: str) -> str:
        # GET 查询幂等：超时/网络抖动时有限次重试；循环层不会再重试。
        last_error: str | None = None
        attempts = config.TOOL_MAX_ATTEMPTS
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.get(
                    config.WEATHER_API_URL,
                    params={"city": city},
                    timeout=10,
                )
                resp.raise_for_status()
                try:
                    return json.dumps(resp.json(), ensure_ascii=False)
                except ValueError:
                    return resp.text
            except requests.RequestException as e:
                last_error = str(e)
                if attempt >= attempts:
                    break
        return json.dumps(
            {"error": "upstream", "message": last_error or "天气服务不可用"},
            ensure_ascii=False,
        )
