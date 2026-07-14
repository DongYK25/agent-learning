"""
最小 Agent 示例：聊天 + 天气 Tool + 会话历史

流程：
1. 用户输入 → 追加到 messages
2. 调用 DeepSeek（带 tools 定义）
3. 若模型要求调工具 → 调用本地天气 API → 把结果写回 messages → 再问模型
4. 得到最终自然语言回答
"""

from __future__ import annotations

import json
import logging
import os
import sys

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://localhost:8091/weather")

if not DEEPSEEK_API_KEY:
    print("请先在 .env 中设置 DEEPSEEK_API_KEY（可参考 .env.example）")
    sys.exit(1)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

# ---------- Tool：调用你本地的天气服务 ----------

def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    try:
        resp = requests.get(WEATHER_API_URL, params={"city": city}, timeout=10)
        resp.raise_for_status()
        # 后端可能返回 JSON 或纯文本，统一转成字符串给模型
        try:
            return json.dumps(resp.json(), ensure_ascii=False)
        except ValueError:
            return resp.text
    except requests.RequestException as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 告诉模型「有哪些工具可用」——这是 Function Calling 的核心
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
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
]

# name → 本地可执行函数
TOOL_IMPL = {
    "get_weather": get_weather,
}


def _messages_for_log(messages: list) -> str:
    """将 messages 转为可读 JSON，便于日志观察。"""
    serializable = []
    for m in messages:
        if isinstance(m, dict):
            serializable.append(m)
        else:
            serializable.append(m.model_dump(exclude_none=True))
    return json.dumps(serializable, ensure_ascii=False, indent=2)


def run_tool(name: str, arguments_json: str) -> str:
    fn = TOOL_IMPL.get(name)
    if fn is None:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    args = json.loads(arguments_json or "{}")
    print(f"  [tool] {name}({args})")
    return fn(**args)


def chat_once(messages: list) -> None:
    """一轮 Agent 循环：可能多次 tool call，直到模型给出最终文本。"""
    while True:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
        )
        msg = response.choices[0].message

        # assistant 消息（可能含 tool_calls）必须原样追加进历史
        messages.append(msg)
        logger.info("messages:\n%s", _messages_for_log(messages))
        if not msg.tool_calls:
            # 没有工具调用 → 这就是最终回答
            print(f"助手: {msg.content}\n")
            return

        # 执行每个 tool，并把结果以 role=tool 写回
        for tc in msg.tool_calls:
            result = run_tool(tc.function.name, tc.function.arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )
        # 带着工具结果继续 while，再问一次模型


def main() -> None:
    # 会话历史：整个对话期间一直累积
    messages: list = [
        {
            "role": "system",
            "content": (
                "你是一个简洁友好的中文助手。"
                "需要天气信息时，必须调用 get_weather 工具，不要编造天气。"
            ),
        }
    ]

    print("DeepSeek Agent 已启动（输入 quit 退出）")
    print(f"模型: {DEEPSEEK_MODEL}")
    print(f"天气服务: {WEATHER_API_URL}\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("再见。")
            break

        messages.append({"role": "user", "content": user_input})
        try:
            chat_once(messages)
        except Exception as e:
            # 出错时去掉刚加的 user，避免历史脏掉
            messages.pop()
            print(f"出错: {e}\n")


if __name__ == "__main__":
    main()
