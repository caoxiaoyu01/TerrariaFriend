from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from agent.models.trigger import GameEventType
from agent.models.trigger_base import CamelModel
from agent.trace.episode import Episode, EpisodeType


RELEVANT_WORLD_EVENT_IDS = frozenset(
    {
        "BloodMoon",
        "SolarEclipse",
        "SlimeRain",
        "PumpkinMoon",
        "FrostMoon",
        "Party",
        "LanternNight",
        "GoblinArmy",
        "PirateInvasion",
        "MartianMadness",
        "FrostLegion",
    }
)


class CloseContext(CamelModel):
    boundary_type: GameEventType
    occurred_at: datetime
    source_episode_id: str = Field(min_length=1)
    primary_entity: str | None = None
    context_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        return value


class BoundaryAction(str, Enum):
    NONE = "NONE"
    CLOSE_READY = "CLOSE_READY"
    CLOSE = "CLOSE"


class BoundaryEvaluation(CamelModel):
    action: BoundaryAction
    close_context: CloseContext | None = None


class TraceBoundaryPolicy:
    """根据现有情节内容判断何时结束一段近期记忆"""

    def evaluate(self, episode: Episode) -> BoundaryEvaluation:
        event = episode.events[0]
        capsule = event.capsule
        source = capsule.source_event_type
        data = capsule.data

        if source == GameEventType.WORLD_SESSION_ENDED.value:
            return BoundaryEvaluation(action=BoundaryAction.CLOSE)

        if source == GameEventType.BOSS_ENDED.value:
            bosses = getattr(getattr(data, "combat", None), "bosses", None)
            if bosses == []:
                return self._close_ready(
                    episode,
                    GameEventType.BOSS_ENDED,
                    {"boss_name": self._entity_name(capsule)},
                )

        if source == GameEventType.PLAYER_DIED.value:
            bosses = getattr(getattr(data, "combat", None), "bosses", None)
            if bosses == []:
                return self._close_ready(
                    episode,
                    GameEventType.PLAYER_DIED,
                    {"active_bosses": []},
                )

        if source == GameEventType.PROGRESS_MILESTONE_CHANGED.value:
            return self._close_ready(
                episode,
                GameEventType.PROGRESS_MILESTONE_CHANGED,
                {
                    "milestone_id": getattr(data, "change_id", None),
                    "milestone_name": getattr(data, "change_name", None),
                    "current_stage": getattr(data, "progression_stage_after", None),
                },
            )

        if source == GameEventType.SCENE_FEATURE_EXITED.value:
            return self._close_ready(
                episode,
                GameEventType.SCENE_FEATURE_EXITED,
                {
                    "feature_category": getattr(data, "feature_category", None),
                    "feature": getattr(data, "feature_name", None),
                },
            )

        if source == GameEventType.WORLD_EVENT_ENDED.value:
            remaining = set(
                getattr(data, "remaining_active_event_ids", [])
            )
            if not remaining.intersection(RELEVANT_WORLD_EVENT_IDS):
                return self._close_ready(
                    episode,
                    GameEventType.WORLD_EVENT_ENDED,
                    {
                        "event_id": getattr(data, "event_id", None),
                        "event_name": getattr(data, "event_name", None),
                        "remaining_active_event_ids": sorted(remaining),
                    },
                )

        return BoundaryEvaluation(action=BoundaryAction.NONE)

    def is_deterministic_continuation(
        self,
        close_context: CloseContext,
        episode: Episode,
    ) -> bool:
        return (
            close_context.boundary_type is GameEventType.BOSS_ENDED
            and episode.episode_type is EpisodeType.EVENT
            and episode.events[0].capsule.source_event_type
            == GameEventType.PROGRESS_MILESTONE_CHANGED.value
        )

    @staticmethod
    def user_query(episode: Episode) -> str | None:
        if episode.episode_type is not EpisodeType.CONVERSATION:
            return None
        capsule = episode.events[0].capsule
        if capsule.source_event_type != "USER_QUERY":
            return None
        content = getattr(capsule.data, "content", None)
        return content if isinstance(content, str) and content.strip() else None

    @staticmethod
    def _entity_name(capsule: Any) -> str | None:
        entity = capsule.primary_entity
        return entity.entity_name if entity is not None else None

    def _close_ready(
        self,
        episode: Episode,
        boundary_type: GameEventType,
        context_data: dict[str, Any],
    ) -> BoundaryEvaluation:
        event = episode.events[0]
        entity = self._entity_name(event.capsule)
        return BoundaryEvaluation(
            action=BoundaryAction.CLOSE_READY,
            close_context=CloseContext(
                boundary_type=boundary_type,
                occurred_at=event.occurred_at,
                source_episode_id=episode.id,
                primary_entity=entity,
                context_data={
                    key: value
                    for key, value in context_data.items()
                    if value is not None
                },
            ),
        )
