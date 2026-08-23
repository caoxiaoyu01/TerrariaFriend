# TerrariaFriend Agent

在本目录启动 P0 FastAPI 后端：

```powershell
uv run agent
```

也可以直接使用现有虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
```

Trigger 接口为 `POST http://127.0.0.1:8000/agent/trigger`。

## Decision Node P0

Decision Node 已接入 SiliconFlow Chat Completions，并使用结构化 JSON 输出完成 `IGNORE / RESPOND / REASON` 分类。

首次配置时复制示例文件：

```powershell
Copy-Item .env.example .env
```

然后只在 `.env` 中填写真实 API Key。`.env` 已被 Git 忽略，`.env.example` 只保存可提交的占位配置。

Decision 模型使用以下独立配置：

```text
TERRARIAFRIEND_DECISION_MODEL
TERRARIAFRIEND_DECISION_API_KEY
TERRARIAFRIEND_DECISION_BASE_URL
TERRARIAFRIEND_DECISION_MAX_TOKENS
TERRARIAFRIEND_DECISION_TEMPERATURE
TERRARIAFRIEND_DECISION_TOP_P
TERRARIAFRIEND_DECISION_TOP_K
TERRARIAFRIEND_DECISION_FREQUENCY_PENALTY
TERRARIAFRIEND_DECISION_ENABLE_THINKING
```

启动时会自动读取 `agent/.env`，系统环境变量具有更高优先级。缺少必需配置时直接启动失败。

运行本地契约测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
