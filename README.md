# DeepSeek Agent（v0.4 Tool 工程化）

聊天 + 天气 / 时间 Tool + Session / Memory + 循环护栏。

v0.4：把 Tool 当后端接口——Pydantic 校验、统一 ToolResult、返回截断；加第二个 Tool 不用改循环。

## 目录结构

```
agent/
  main.py           # 入口与 Agent 循环
  config.py         # 环境变量
  session.py        # Session（session_id → memory / setting）
  logger.py         # 结构化 Debug 日志
  llm/client.py     # LLM 客户端
  memory/history.py # 内存版 Memory（调试）
  memory/postgres.py# PgMemory（sessions + messages）
  tool/
    weather.py      # WeatherTool（Pydantic 参数 + execute）
    time.py         # TimeTool（对照：加 Tool 只注册）
    result.py       # 统一 ToolResult
    schema.py       # Pydantic → OpenAI function schema
    registry.py     # 校验 / 重试 / 截断 / 只读并行
  prompt/
    assistant.txt   # 系统提示词（可换成 coder / planner）
```

## 准备

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 复制环境变量并填入 Key：

```bash
copy .env.example .env
```

编辑 `.env`，填入 `DEEPSEEK_API_KEY`，并按需改 `DATABASE_URL`（默认 `127.0.0.1:5432/server`）。

3. PostgreSQL 已建好 `sessions`、`messages` 表（见对话中的 DDL）。

4. 确保天气服务已启动：`http://localhost:8091/weather?city=北京`

## 运行

```bash
python agent.py
# 或
python -m agent.main
```

试试：

- `北京天气怎么样？` → 应触发 `get_weather`
- `现在几点？` → 应触发 `get_current_time`（不改 `chat_once`）
- `北京天气，顺便现在几点` → 一轮两个只读 Tool，可并发
- `那上海呢？` → 利用会话历史，再查上海
- `1+1等于几？` → 不调工具，直接回答

验收（对照 `docs/TUTORIAL.md` v0.4）：

- 模型传空城市 / 过长城市 → `validation_error` 回给模型，终端无 Python traceback
- 停掉天气服务 → `upstream_error` 或 `timeout`，会话可继续
- 新 Tool 只新增模块并 `register`，不改循环主流程

## 代码在学什么

| 概念 | 对应位置 |
|------|----------|
| Session | `session.py`，每人/每次对话一个 `session_id` |
| Memory | `memory/postgres.py`，会话消息落 PG；Agent 不直接改 messages |
| JSON Schema / Pydantic | `tool/weather.py` 的 `WeatherArgs`；schema 由模型生成 |
| ToolResult | `tool/result.py`：ok / validation_error / timeout / upstream_error |
| Tool 注册 | `tool/registry.py`，新 Tool 注册即可 |
| 并行 tool_calls | 全部 `parallel_safe` 时 `execute_many` 并发，否则串行 |
| 幂等 | 仅 `idempotent=True` 的超时/上游错误由 Registry 重试 |
| Agent 循环 | `main.py` 的 `chat_once`：max steps / 连续失败则停 |
| Debug 日志 | `logger.py` + `agent.log`（USER / LLM / Tool / LOOP 分段） |
