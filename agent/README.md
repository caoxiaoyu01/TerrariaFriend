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
