"""
Agent 入口：Session + Memory + Tool Registry + LLM 循环。

流程：
1. 用户输入 → session.add_user()
2. 调用 LLM（带 registry.schemas）
3. 若模型要求调工具 → registry.execute → session.add_tool() → 再问模型
4. 得到最终自然语言回答，或被 max steps / 连续失败护栏打断
"""

from __future__ import annotations  # 让类型注解可以用「尚未定义」的名字（如 Session）

import json
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

_MSG_MAX_STEPS = "本轮工具调用已达上限，已停止。请换个更具体的问题，或稍后再试。"
_MSG_CONSECUTIVE = "工具连续失败，本轮已停止。你可以稍后再问，或先聊别的。"
_MSG_LLM_ERROR = "模型服务暂时不可用，请稍后再试。"


class LoopAborted(Exception):
    """第一次 LLM 调用失败：Memory 里还只有刚写入的 user，调用方应 pop_last。"""


def _tool_result_is_error(result: str) -> bool:
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and bool(data.get("error"))


def _close_turn(session: Session, agent_log: AgentLogger, text: str) -> None:
    session.add_assistant({"role": "assistant", "content": text})
    agent_log.llm_reply(text)
    print(f"助手: {text}\n")


def chat_once(
    session: Session,
    llm: LLMClient,
    registry: ToolRegistry,
    agent_log: AgentLogger,
) -> None:
    """一轮用户输入对应的 Agent 循环：有限步内结束；Tool 失败回写成消息而不是崩溃。"""
    max_steps = config.MAX_STEPS
    max_consecutive = config.MAX_CONSECUTIVE_TOOL_ERRORS
    consecutive_errors = 0
    step = 0

    while True:
        step += 1
        try:
            # 1) 把当前会话全部消息发给模型，同时附上工具 schema。
            response = llm.chat(session.load(), tools=registry.schemas)
        except Exception as e:
            agent_log.loop_stop(step, max_steps, "llm_error", str(e))
            if step == 1:
                # 还没有任何 assistant：撤回 user，避免空问句留在历史里。
                raise LoopAborted(str(e)) from e
            # 已有完整的 LLM↔Tool 轮次：补一句人话收尾，协议保持完整。
            _close_turn(session, agent_log, _MSG_LLM_ERROR)
            return

        # 2) OpenAI 兼容协议：choices[0].message 才是这一轮助手回复。
        msg = response.choices[0].message

        # 3) 没有 tool_calls → 最终自然语言，写入后结束。
        if not msg.tool_calls:
            session.add_assistant(msg)
            agent_log.loop_step(step, max_steps, "final")
            agent_log.llm_reply(msg.content)
            print(f"助手: {msg.content}\n")
            return

        # 4) 已是最后一步仍要调工具：不要写入这条 tool_calls（否则缺 tool 结果会污染协议）。
        if step >= max_steps:
            agent_log.llm_tool_calls(msg.tool_calls)
            agent_log.loop_stop(step, max_steps, "max_steps")
            print(f"  [stop] max_steps at step {step}/{max_steps}")
            _close_turn(session, agent_log, _MSG_MAX_STEPS)
            return

        # 5) 写入带 tool_calls 的 assistant，随后必须配齐全部 tool 消息。
        session.add_assistant(msg)
        agent_log.loop_step(step, max_steps, "tool_calls")
        agent_log.llm_tool_calls(msg.tool_calls)
        print(f"  [step {step}/{max_steps}]")

        for tc in msg.tool_calls:
            try:
                result = registry.execute(tc.function.name, tc.function.arguments)
            except Exception as e:
                # Registry 已兜底；这里再防一层，保证每条 tool_call_id 都有结果。
                result = json.dumps(
                    {"error": "execute_failed", "message": str(e)},
                    ensure_ascii=False,
                )
            agent_log.tool(tc.function.name, tc.function.arguments, result)
            print(f"  [tool] {tc.function.name}({tc.function.arguments})")
            session.add_tool(tc.id, result)
            if _tool_result_is_error(result):
                consecutive_errors += 1
            else:
                consecutive_errors = 0

        # 6) 连续失败：本轮 tool 结果已写全，用人话收尾，会话可继续。
        if consecutive_errors >= max_consecutive:
            agent_log.loop_stop(
                step,
                max_steps,
                "consecutive_tool_errors",
                f"consecutive={consecutive_errors}",
            )
            print(
                f"  [stop] consecutive_tool_errors={consecutive_errors} "
                f"at step {step}/{max_steps}"
            )
            _close_turn(session, agent_log, _MSG_CONSECUTIVE)
            return

        # 7) while 继续：带着工具结果再问模型。


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
    print(f"memory: PostgreSQL ({config.DATABASE_URL.split('@')[-1]})")
    print(
        f"护栏: max_steps={config.MAX_STEPS} "
        f"consecutive_tool_errors={config.MAX_CONSECUTIVE_TOOL_ERRORS} "
        f"llm_timeout={config.LLM_TIMEOUT_SECONDS}s\n"
    )

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

            # 用户话先入库，再进 Agent 循环。仅第一次 LLM 失败时才 pop_last。
            session.add_user(user_input)
            agent_log.user(user_input)
            try:
                chat_once(session, llm, registry, agent_log)
            except LoopAborted as e:
                # 第一次 LLM 调用失败：本轮还没有 assistant，撤回 user。
                session.pop_last()
                print(f"出错: {e}\n")
            except Exception as e:
                # 已写入过 assistant/tool 时不要 pop_last，避免拆掉成对的 tool_calls。
                print(f"出错: {e}\n")
    finally:
        # 无论正常退出还是异常，都关掉数据库连接，避免连接泄漏。
        memory.close()


if __name__ == "__main__":
    # 直接运行本文件时才进 main；被别人 import 时只加载函数，不启动 REPL。
    main()
