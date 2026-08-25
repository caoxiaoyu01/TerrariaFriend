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

## Phase 2A

后端使用 Decision Node 完成 `IGNORE / RESPOND / REASON` 分类，RESPOND 进入 Response Generator，REASON 进入 LangGraph Reasoning Loop。

首次配置时复制示例文件：

```powershell
Copy-Item .env.example .env
```

然后只在 `.env` 中填写真实 API Key。`.env` 已被 Git 忽略，`.env.example` 只保存可提交的占位配置。

三个角色共用以下 SiliconFlow 凭证：

```text
TERRARIAFRIEND_LLM_API_KEY
TERRARIAFRIEND_LLM_BASE_URL
```

Decision、Response 和 Reasoning 分别使用 `TERRARIAFRIEND_DECISION_*`、`TERRARIAFRIEND_RESPONSE_*`、`TERRARIAFRIEND_REASONING_*` 配置。旧的 `TERRARIAFRIEND_DECISION_API_KEY` 和 `TERRARIAFRIEND_DECISION_BASE_URL` 仍可作为共享凭证兼容读取。

启动时会自动读取 `agent/.env`，系统环境变量具有更高优先级。缺少必需配置时直接启动失败。

运行本地契约测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
