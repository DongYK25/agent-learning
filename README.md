# DeepSeek Agent（v0.3 循环加固）

聊天 + 天气 Tool（本地天气服务）+ Session / Memory + 会话历史。

v0.3：Agent 循环有步数上限和连续失败护栏；Tool 失败回写成消息，不把进程打挂。

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
    weather.py      # WeatherTool（schema + execute）
    registry.py     # 注册表，自动生成 tools 列表
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
- `那上海呢？` → 利用会话历史，再查上海
- `1+1等于几？` → 不调工具，直接回答

护栏验收（对照 `docs/TUTORIAL.md` v0.3）：

- 把 `AGENT_MAX_STEPS` 设成 `2` 再连问天气 → 有限步内停止，终端/`agent.log` 有 `reason=max_steps`
- 停掉天气服务再问北京天气 → 不崩溃，会话还能继续问 `1+1`
- 失败后历史里不应出现「assistant 带了 tool_calls 却没有对应 tool 消息」

## 代码在学什么

| 概念 | 对应位置 |
|------|----------|
| Session | `session.py`，每人/每次对话一个 `session_id` |
| Memory | `memory/postgres.py`，会话消息落 PG；Agent 不直接改 messages |
| Tool 抽象 | `tool/weather.py` 的 `schema` + `execute` |
| Tool 注册 | `tool/registry.py`，新 Tool 注册即可 |
| Prompt | `prompt/*.txt`，可按角色切换 |
| Agent 循环 | `main.py` 的 `chat_once`：max steps / 连续失败则停 |
| Debug 日志 | `logger.py` + `agent.log`（USER / LLM / Tool / LOOP 分段） |
