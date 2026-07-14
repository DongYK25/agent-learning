"""
Agent 入口：Session + Memory + Tool Registry + LLM 循环。

流程：
1. 用户输入 → session.add_user()
2. 调用 LLM（带 registry.schemas）
3. 若模型要求调工具 → registry.execute → session.add_tool() → 再问模型
4. 得到最终自然语言回答
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许 `python agent/main.py` 直接运行（否则找不到 agent 包）
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config
from agent.llm import LLMClient
from agent.logger import AgentLogger
from agent.memory import Memory
from agent.prompt import load_prompt
from agent.session import Session, SessionSetting
from agent.tool.registry import ToolRegistry, build_default_registry


def chat_once(
    session: Session,
    llm: LLMClient,
    registry: ToolRegistry,
    agent_log: AgentLogger,
) -> None:
    """一轮 Agent 循环：可能多次 tool call，直到模型给出最终文本。"""
    while True:
        response = llm.chat(session.load(), tools=registry.schemas)
        msg = response.choices[0].message
        session.add_assistant(msg)

        if not msg.tool_calls:
            agent_log.llm_reply(msg.content)
            print(f"助手: {msg.content}\n")
            return

        agent_log.llm_tool_calls(msg.tool_calls)
        for tc in msg.tool_calls:
            result = registry.execute(tc.function.name, tc.function.arguments)
            agent_log.tool(tc.function.name, tc.function.arguments, result)
            print(f"  [tool] {tc.function.name}({tc.function.arguments})")
            session.add_tool(tc.id, result)


def main() -> None:
    memory = Memory()
    session = Session(
        memory=memory,
        setting=SessionSetting(prompt_name=config.DEFAULT_PROMPT),
    )
    session.add_system(load_prompt(session.setting.prompt_name))

    llm = LLMClient()
    registry = build_default_registry()
    agent_log = AgentLogger()

    print("DeepSeek Agent 已启动（输入 quit 退出）")
    print(f"模型: {llm.model}")
    print(f"天气服务: {config.WEATHER_API_URL}")
    print(f"session: {session.session_id}\n")

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

        session.add_user(user_input)
        agent_log.user(user_input)
        try:
            chat_once(session, llm, registry, agent_log)
        except Exception as e:
            session.pop_last()
            print(f"出错: {e}\n")


if __name__ == "__main__":
    main()
