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
            return json.dumps({"error": str(e)}, ensure_ascii=False)
