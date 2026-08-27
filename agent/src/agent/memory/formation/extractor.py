from typing import Any

from pydantic import ValidationError

from agent.llm.client import RoleLLMClient, parse_json_object
from agent.memory.formation.prompt import MEMORY_EXTRACTION_PROMPT
from agent.memory.formation.schema import (
    MemoryExtractionInput,
    MemoryExtractionResult,
    MemoryRelationType,
)
from agent.trace.capsule.schema import CapsuleType
from agent.models.trigger import GameEventType


class MemoryExtractionError(RuntimeError):
    pass


class MemoryExtractor:
    """执行一次不使用工具的结构化二级价值和关系提取调用"""

    def __init__(self, model_client: RoleLLMClient) -> None:
        self.model_client = model_client

    async def extract(
        self,
        extraction_input: MemoryExtractionInput,
    ) -> MemoryExtractionResult:
        input_data = _model_input(extraction_input)
        try:
            completion = await self.model_client.generate_structured(
                system_prompt=MEMORY_EXTRACTION_PROMPT,
                input_data=input_data,
                output_schema=MemoryExtractionResult.model_json_schema(),
            )
            result = MemoryExtractionResult.model_validate(
                parse_json_object(completion.content)
            )
            _validate_evidence(result, set(input_data["allowed_evidence_episode_ids"]))
            _validate_defeat_evidence(result, extraction_input)
            return result
        except (ValidationError, ValueError, KeyError, TypeError) as exception:
            raise MemoryExtractionError(
                f"Invalid Memory Extractor output: {exception}"
            ) from exception


def _model_input(extraction_input: MemoryExtractionInput) -> dict[str, Any]:
    episode = extraction_input.episode
    target = extraction_input.related_episode_context
    allowed_ids = [episode.id]
    if target is not None:
        allowed_ids.append(target.id)
    return {
        "current_episode": _episode_projection(episode),
        "related_episode_context": (
            _episode_projection(target) if target is not None else None
        ),
        "episode_relations": [
            relation.model_dump(mode="json", by_alias=True)
            for relation in extraction_input.episode_relations
        ],
        "allowed_evidence_episode_ids": allowed_ids,
    }


def _episode_projection(episode) -> dict[str, Any]:
    # 触发事件是客观的情节主体
    # 智能体响应文本 工具历史 维基输出和执行推理均有意省略
    event = episode.events[0]
    capsule = event.capsule
    return {
        "episode_id": episode.id,
        "episode_type": episode.episode_type.value,
        "occurred_at": event.occurred_at.isoformat(),
        "source_event_type": capsule.source_event_type,
        "primary_entity": (
            capsule.primary_entity.model_dump(mode="json", by_alias=True)
            if capsule.primary_entity is not None
            else None
        ),
        "facts": _capsule_facts(capsule),
    }


def _capsule_facts(capsule) -> dict[str, Any]:
    data = capsule.data
    if capsule.capsule_type is CapsuleType.CONVERSATION:
        return {
            "role": data.role,
            "content": data.content,
        }
    if capsule.capsule_type is CapsuleType.COMBAT:
        return {
            "event_state": data.event_state,
            "active_bosses": [boss.name for boss in data.combat.bosses],
        }
    if capsule.capsule_type is CapsuleType.PROGRESS:
        return {
            "change_category": data.change_category,
            "change_id": data.change_id,
            "change_name": data.change_name,
            "unlocked": data.after.unlocked,
        }
    if capsule.capsule_type is CapsuleType.EXPLORATION:
        return {
            key: value
            for key, value in {
                "discovery_kind": data.discovery_kind,
                "feature_category": getattr(data, "feature_category", None),
                "feature_name": getattr(data, "feature_name", None),
                "cell": (
                    data.cell.model_dump(mode="json", by_alias=True)
                    if getattr(data, "cell", None) is not None
                    else None
                ),
            }.items()
            if value is not None
        }
    if capsule.capsule_type is CapsuleType.EQUIPMENT:
        return {
            "armor_before": (
                data.armor_before.model_dump(mode="json", by_alias=True)
                if data.armor_before is not None else None
            ),
            "armor_after": (
                data.armor_after.model_dump(mode="json", by_alias=True)
                if data.armor_after is not None else None
            ),
            "accessories_added": [
                item.model_dump(mode="json", by_alias=True)
                for item in data.accessories_added
            ],
            "accessories_removed": [
                item.model_dump(mode="json", by_alias=True)
                for item in data.accessories_removed
            ],
        }
    if capsule.capsule_type is CapsuleType.WORLD_EVENT:
        return {
            "event_id": data.event_id,
            "event_name": data.event_name,
        }
    return {}


def _validate_evidence(
    result: MemoryExtractionResult,
    allowed_episode_ids: set[str],
) -> None:
    for relation in result.relations:
        if not set(relation.evidence_episode_ids).issubset(allowed_episode_ids):
            raise ValueError("模型返回了输入范围外的 evidence Episode ID")


def _validate_defeat_evidence(
    result: MemoryExtractionResult,
    extraction_input: MemoryExtractionInput,
) -> None:
    episodes = {extraction_input.episode.id: extraction_input.episode}
    if extraction_input.related_episode_context is not None:
        episodes[extraction_input.related_episode_context.id] = (
            extraction_input.related_episode_context
        )
    for relation in result.relations:
        if relation.relation_type is not MemoryRelationType.DEFEATED:
            continue
        evidence = [episodes[episode_id] for episode_id in relation.evidence_episode_ids]
        if not any(_is_valid_defeat_evidence(episode) for episode in evidence):
            raise ValueError("DEFEATED 缺少 BossDefeated、boss progress 或玩家明确陈述证据")


def _is_valid_defeat_evidence(episode) -> bool:
    capsule = episode.events[0].capsule
    if capsule.source_event_type == GameEventType.BOSS_DEFEATED.value:
        return True
    if (
        capsule.source_event_type == GameEventType.PROGRESS_MILESTONE_CHANGED.value
        and getattr(capsule.data, "change_category", None) == "boss"
    ):
        return True
    return capsule.source_event_type == "USER_QUERY"
