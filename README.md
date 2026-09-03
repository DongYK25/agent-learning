# DeepSeek Agent（v0.5 HTTP + 多用户 Session）

聊天 + 天气 / 时间 Tool + Session / Memory。HTTP 无状态，历史在 PostgreSQL；客户端持有 `session_id`。

v0.5：FastAPI 暴露创建会话 / 发消息 / 拉历史。CLI 仍可作调试。

## 目录结构

```
agent/
  api.py            # FastAPI：/sessions、/messages
  static/index.html # 最小前端（可开两个标签页对照）
  main.py           # CLI 与 Agent 循环
  ...
```

## 准备

```bash
pip install -r requirements.txt
copy .env.example .env
```

填入 `DEEPSEEK_API_KEY`，确认 PostgreSQL 的 `sessions` / `messages` 表和天气服务可用。

## 运行

HTTP（产品形态）：

```bash
python -m agent.api
# 或
uvicorn agent.api:app --host 127.0.0.1 --port 8090
```

打开 http://127.0.0.1:8000/ ，或用 curl：

```bash
curl -s -X POST http://127.0.0.1:8000/sessions -H "Content-Type: application/json" -d "{}"
# 记下 session_id

curl -s -X POST http://127.0.0.1:8000/sessions/<session_id>/messages ^
  -H "Content-Type: application/json" ^
  -d "{\"content\":\"北京天气怎么样？\"}"

curl -s http://127.0.0.1:8000/sessions/<session_id>/messages
```

两个 session 交叉提问，历史不得串台。重启 uvicorn 后，用原来的 `session_id` 问「那上海呢？」应仍能接上。

CLI 调试：

```bash
python agent.py
```

## 已知缺口（本版承认，不修）

- **同步阻塞：** 一次用户消息可能多步 LLM↔Tool，HTTP 要等整段结束。代理/浏览器可能先超时。v0.6 用流式（SSE）改善体感。
- **无鉴权：** 知道 `session_id` 就能读写。v1.0 再加 API Key。
- **无流式 / 无 RAG。**

## 代码在学什么

| 概念 | 对应位置 |
|------|----------|
| Session ID | 客户端保存，每次请求带上；`POST /sessions` 创建 |
| 多租户（入门） | 按 `session_id` 隔离，不串历史 |
| 无状态 HTTP vs 有状态会话 | 接口不记进程内存；`PgMemory` 每条操作独立连 PG |
| Agent 循环 | `main.py` 的 `chat_once` / `run_user_turn`，HTTP 与 CLI 共用 |
