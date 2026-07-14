# DeepSeek 最小 Agent 示例

聊天 + 天气 Tool（本地 `localhost:8091`）+ 会话历史。

## 准备

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 复制环境变量并填入 Key：

```bash
copy .env.example .env
```

编辑 `.env`，填入 `DEEPSEEK_API_KEY`。

3. 确保天气服务已启动：`http://localhost:8091/weather?city=北京`

## 运行

```bash
python agent.py
```

试试：

- `北京天气怎么样？` → 应触发 `get_weather`
- `那上海呢？` → 利用会话历史，再查上海
- `1+1等于几？` → 不调工具，直接回答

## 代码在学什么

| 概念 | 对应位置 |
|------|----------|
| 会话历史 | `messages` 列表整段对话累积 |
| Tool 定义 | `TOOLS`，描述给模型看 |
| Tool 执行 | `run_tool` → 请求你的天气 API |
| Agent 循环 | `chat_once` 里的 `while`：有 tool_calls 就继续 |
