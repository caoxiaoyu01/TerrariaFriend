from fastapi import FastAPI

from agent.models.trigger import AgentResponse, TriggerRequest

app = FastAPI(title="TerrariaFriend Agent")


@app.post("/agent/trigger", response_model=AgentResponse)
async def handle_trigger(trigger: TriggerRequest) -> AgentResponse:
    """接收 Mod Trigger；P0 暂时返回固定连通性响应。"""
    return AgentResponse(
        action="RESPOND",
        message="TerrariaFriend backend connected.",
        success=True,
        error=None,
    )
