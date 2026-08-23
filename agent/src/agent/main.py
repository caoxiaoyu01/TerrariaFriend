import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI
from fastapi import Depends
from pydantic import ValidationError

from agent.decision.node import DecisionNode, DecisionNodeError
from agent.decision.schema import DecisionAction, DecisionInput, DecisionResult
from agent.models.trigger import AgentResponse, TriggerRequest, TriggerType


logger = logging.getLogger("uvicorn.error")
HP_DROP_REASON_THRESHOLD = -0.10

# 全局复用 Decision Node 并通过 FastAPI Depends 支持测试替换
decision_node = DecisionNode.from_environment()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await decision_node.aclose()


app = FastAPI(title="TerrariaFriend Agent", lifespan=lifespan)


def get_decision_node() -> DecisionNode:
    return decision_node


def _as_json(value: object, max_length: int = 600) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def _log_decision_input(decision_input: DecisionInput) -> None:
    trigger_type = decision_input.trigger_type
    vitals = _as_json(decision_input.vitals.model_dump())
    if trigger_type is TriggerType.USER_QUERY:
        logger.info(
            "[DecisionNode] trigger=%s\nquery: %s\nvitals: %s",
            trigger_type.value,
            decision_input.user_query,
            vitals,
        )
    elif trigger_type is TriggerType.GAME_EVENT:
        game_event = decision_input.game_event
        logger.info(
            "[DecisionNode] trigger=%s\nevent_type: %s\npayload: %s\ncontext: %s\nvitals: %s",
            trigger_type.value,
            game_event.event_type.value,
            _as_json(game_event.payload),
            _as_json(decision_input.event_context.model_dump(exclude_none=True)),
            vitals,
        )
    else:
        logger.info(
            "[DecisionNode] trigger=%s\nsummary: %s\nvitals: %s",
            trigger_type.value,
            _as_json(decision_input.periodic_summary.model_dump(exclude_none=True)),
            vitals,
        )

    logger.debug(
        "[DecisionNode] input=%s",
        _as_json(decision_input.model_dump(mode="json", exclude_none=True), 2000),
    )


def _apply_health_rule(
    decision_input: DecisionInput,
) -> DecisionResult | None:
    hp_delta = decision_input.vitals.hp_delta
    if hp_delta > HP_DROP_REASON_THRESHOLD:
        return None

    logger.info(
        "[DecisionNode] hard_rule=HP_DROP hp_delta=%.3f",
        hp_delta,
    )
    return DecisionResult(
        action=DecisionAction.REASON,
        reason="玩家近期明显掉血，需要获取更多战斗和生存状态分析原因",
    )


@app.post("/agent/trigger", response_model=AgentResponse)
async def handle_trigger(
    trigger: TriggerRequest,
    node: Annotated[DecisionNode, Depends(get_decision_node)],
) -> AgentResponse:
    """接收 Trigger 并交给 Decision Node 选择处理路径"""
    try:
        # Route 只负责输入转换和调用编排
        decision_input = DecisionInput.from_trigger(trigger)
        _log_decision_input(decision_input)
        started_at = time.perf_counter()
        result = _apply_health_rule(decision_input)
        if result is None:
            result = await node.decide(decision_input)
            decision_source = node.model_name
        else:
            decision_source = "code:HP_DROP"
    except (DecisionNodeError, ValidationError) as exception:
        # 模型或 Schema 失败时返回业务错误 避免 FastAPI 进程崩溃
        logger.error("Decision Node failed: %s", exception)
        return AgentResponse(
            action="ERROR",
            message=None,
            decision_reason=None,
            success=False,
            error=str(exception),
        )

    latency = time.perf_counter() - started_at
    logger.info(
        "[DecisionNode] result\naction: %s\nreason: %s\nmodel: %s\nlatency: %.2fs",
        result.action.value,
        result.reason,
        decision_source,
        latency,
    )

    # P0 只返回路径标记 暂不生成最终回复
    message = {
        DecisionAction.IGNORE: None,
        DecisionAction.RESPOND: "[DecisionNode] RESPOND",
        DecisionAction.REASON: "[DecisionNode] REASON",
    }[result.action]

    return AgentResponse(
        action=result.action.value,
        message=message,
        decision_reason=result.reason,
        success=True,
        error=None,
    )
