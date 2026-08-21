"""
Agent 入口：Session + Memory + Tool Registry + LLM 循环。

流程：
1. 用户输入 → session.add_user()
2. 调用 LLM（带 registry.schemas）
3. 若模型要求调工具 → registry.execute → session.add_tool() → 再问模型
4. 得到最终自然语言回答
"""

from __future__ import annotations  # 让类型注解可以用「尚未定义」的名字（如 Session）

import sys
from pathlib import Path

# 用 `python agent/main.py` 直接跑时，Python 不会把项目根目录放进 sys.path，
# 下面这行 import agent.xxx 就会失败。把仓库根目录插到最前面即可。
# `python -m agent.main` 时 __package__ 不为 None，不会走进这个分支。
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config  # 环境变量：API Key、模型名、数据库 URL、天气服务地址
from agent.llm import LLMClient  # 封装 DeepSeek / OpenAI 兼容的 chat.completions
from agent.logger import AgentLogger  # 把 USER / LLM / Tool 分段写进 agent.log
from agent.memory import PgMemory  # PostgreSQL 持久化对话历史
from agent.prompt import load_prompt  # 从 agent/prompt/*.txt 读 system prompt
from agent.session import Session, SessionSetting  # 会话对象：不直接碰 messages 列表
from agent.tool.registry import ToolRegistry, build_default_registry  # 工具注册与执行


def chat_once(
    session: Session,
    llm: LLMClient,
    registry: ToolRegistry,
    agent_log: AgentLogger,
) -> None:
    """一轮用户输入对应的 Agent 循环：可能多次 tool call，直到模型给出最终文本。"""
    while True:
        # 1) 把当前会话全部消息（system / user / assistant / tool）发给模型，
        #    同时附上工具 JSON Schema，模型才知道有哪些函数可调。
        response = llm.chat(session.load(), tools=registry.schemas)

        # 2) OpenAI 兼容协议：choices[0].message 才是这一轮助手回复。
        #    可能是纯文本，也可能带 tool_calls（要调哪个工具、参数是什么）。
        msg = response.choices[0].message

        # 3) 先把助手这条消息写入 Memory。若带 tool_calls，后续才能用 tool_call_id 对上。
        session.add_assistant(msg)

        # 4) 没有 tool_calls → 模型已经给出最终自然语言，打印并结束本轮。
        if not msg.tool_calls:
            agent_log.llm_reply(msg.content)
            print(f"助手: {msg.content}\n")
            return

        # 5) 有 tool_calls：先记日志，再逐个执行。模型一次可能请求多个工具。
        agent_log.llm_tool_calls(msg.tool_calls)
        for tc in msg.tool_calls:
            # 按名字在 Registry 里找到工具，解析 JSON 参数并真正执行（如调天气 HTTP）。
            result = registry.execute(tc.function.name, tc.function.arguments)
            agent_log.tool(tc.function.name, tc.function.arguments, result)
            print(f"  [tool] {tc.function.name}({tc.function.arguments})")
            # 把工具返回值写成 role=tool 的消息，tool_call_id 必须等于 tc.id。
            session.add_tool(tc.id, result)

        # 6) while 继续：带着「助手要调工具 + 工具结果」再问一次模型，
        #    直到某次回复不再带 tool_calls。


def main() -> None:
    # —— 启动时只做一次：搭好 Memory / Session / LLM / 工具 / 日志 ——

    # 连上 PostgreSQL。后续所有 add_* / load 都走这张表，进程退出前要 close。
    memory = PgMemory()

    # 本会话用哪份 system prompt、默认模型（可被 SessionSetting 覆盖）。
    setting = SessionSetting(prompt_name=config.DEFAULT_PROMPT)

    # 新建会话：自动生成 session_id（UUID），后续消息都挂在这个 id 下。
    session = Session(memory=memory, setting=setting)

    # 在 sessions 表里插入一行元数据（prompt_name、model），没有则创建。
    memory.ensure_session(
        session.session_id,
        prompt_name=setting.prompt_name,
        model=setting.model,
    )

    # 把 prompt 文件内容写成第一条 role=system 的消息，模型之后每轮都能看到人设/规则。
    session.add_system(load_prompt(session.setting.prompt_name))

    llm = LLMClient()  # 读 .env 里的 API Key / 模型名，后面 chat_once 用它调模型
    registry = build_default_registry()  # 目前注册 WeatherTool；schemas 会交给模型
    agent_log = AgentLogger()  # 终端 print 给人看，文件日志给排错看

    print("DeepSeek Agent 已启动（输入 quit 退出）")
    print(f"模型: {llm.model}")
    print(f"天气服务: {config.WEATHER_API_URL}")
    print(f"session: {session.session_id}")
    print(f"memory: PostgreSQL ({config.DATABASE_URL.split('@')[-1]})\n")

    try:
        # —— REPL：反复读用户输入，每条触发一次 chat_once ——
        while True:
            try:
                user_input = input("你: ").strip()
            except (EOFError, KeyboardInterrupt):
                # Ctrl+C / Ctrl+D / 管道结束：正常退出，不要当异常抛出去。
                print("\n再见。")
                break

            if not user_input:
                continue  # 空回车不浪费一次 LLM 调用
            if user_input.lower() in {"quit", "exit", "q"}:
                print("再见。")
                break

            # 用户话先入库，再进 Agent 循环。失败时下面会 pop_last 把这条撤回。
            session.add_user(user_input)
            agent_log.user(user_input)
            try:
                chat_once(session, llm, registry, agent_log)
            except Exception as e:
                # LLM / 网络 / 工具任一失败：删掉刚写入的那条 user 消息，避免脏历史。
                session.pop_last()
                print(f"出错: {e}\n")
    finally:
        # 无论正常退出还是异常，都关掉数据库连接，避免连接泄漏。
        memory.close()


if __name__ == "__main__":
    # 直接运行本文件时才进 main；被别人 import 时只加载函数，不启动 REPL。
    main()
