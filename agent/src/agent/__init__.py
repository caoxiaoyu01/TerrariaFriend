import uvicorn


def main() -> None:
    """启动本地 TerrariaFriend Agent 服务"""
    uvicorn.run("agent.main:app", host="127.0.0.1", port=8000)
