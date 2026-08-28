import uvicorn


def main() -> None:
    """启动本地智能体服务"""
    uvicorn.run("agent.main:app", host="127.0.0.1", port=8000)
