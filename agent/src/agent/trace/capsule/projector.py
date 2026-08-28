from collections.abc import Mapping
from datetime import datetime
from typing import Any

from agent.models.game_snapshot import GameSnapshot
from agent.models.execution import AgentExecutionResult
from agent.models.trigger import (
    EventContext,
    GameEventRequest,
    GameEventType,
    TriggerRequest,
)
from agent.trace.capsule.schema import (
    AreaCell,
    AreaExplorationData,
    ArmorState,
    BossState,
    CapsuleEntityRef,
    CapsuleType,
    CombatCapsule,
    CombatCapsuleData,
    CombatLoadoutState,
    CombatPlayerState,
    CombatState,
    ExplorationCapsule,
    EquipmentCapsule,
    EquipmentCapsuleData,
    ConversationCapsule,
    ConversationCapsuleData,
    HealingState,
    ItemState,
    ProgressCapsule,
    ProgressCapsuleData,
    ProgressUnlockState,
    RecentDamageState,
    SceneFeatureExplorationData,
    SceneState,
    WorldEventCapsule,
    WorldEventCapsuleData,
)


WORLD_MILESTONE_IDS = frozenset(
    {
        "hardmode_started",
        "mechanical_bosses_cleared",
        "plantera_defeated",
        "lunatic_cultist_defeated",
    }
)

CONVERSATION_CONTEXT_FIELDS = {
    "player": (
        "isDead", "life", "maxLife", "mana", "maxMana", "defense",
        "heldItem", "buffs",
    ),
    "combat": (
        "inCombat", "combatDurationSeconds", "bossActive", "activeBosses",
        "nearbyEnemyCount", "hpRatio", "recentDamage",
    ),
    "inventory": (
        "armor", "accessories", "healing", "mana", "bossSummons",
    ),
    "progress": (
        "defeatedBosses", "worldMilestones", "currentStage", "visitedRegions",
    ),
    "scene": ("biomes", "layer", "miniBiomes", "specialAreas", "nearbyBuffs"),
    "world": ("time", "weather", "activeEvents"),
}


def current_stage_id(snapshot: GameSnapshot) -> str:
    """读取游戏端整理好的当前进度阶段"""

    current_stage = _mapping(snapshot.progress, "currentStage")
    stage_id = current_stage.get("id")
    if not isinstance(stage_id, str) or not stage_id:
        raise ValueError("progress.currentStage.id 必须是非空字符串")
    return stage_id


def project_combat_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> CombatCapsule:
    # 死亡快照来自死亡钩子触发后的即时采集
    # 死亡前发生的事只参考最近几秒的受伤记录
    del context
    player = snapshot.player
    combat = snapshot.combat
    inventory = snapshot.inventory
    recent_damage = _mapping(combat, "recentDamage")
    armor = _mapping(inventory, "armor")
    healing = _mapping(inventory, "healing")
    event_states = {
        GameEventType.BOSS_SPAWNED: "boss_spawned",
        GameEventType.BOSS_ENDED: "boss_disappeared",
        GameEventType.BOSS_DEFEATED: "boss_defeated",
        GameEventType.PLAYER_DIED: "player_died",
    }
    entity_type = "player" if event.event_type is GameEventType.PLAYER_DIED else "boss"
    return CombatCapsule(
        capsule_type=CapsuleType.COMBAT,
        captured_at=captured_at,
        snapshot_tick=snapshot.tick,
        source_event_type=event.event_type.value,
        primary_entity=_event_entity(event, entity_type),
        data=CombatCapsuleData(
            event_state=event_states[event.event_type],
            player=CombatPlayerState(
                is_dead=bool(player["isDead"]),
                life=int(player["life"]),
                max_life=int(player["maxLife"]),
                hp_ratio=float(combat["hpRatio"]),
                mana=int(player["mana"]),
                max_mana=int(player["maxMana"]),
                defense=int(player["defense"]),
            ),
            combat=CombatState(
                in_combat=bool(combat["inCombat"]),
                bosses=[BossState.model_validate(item) for item in _list(combat, "activeBosses")],
                nearby_enemy_count=int(combat["nearbyEnemyCount"]),
                recent_damage=RecentDamageState(
                    damage_taken_last_5s=int(recent_damage["damageTakenLast5s"]),
                    last_damage_amount=int(recent_damage["lastDamageAmount"]),
                    last_damage_source=_optional_string(recent_damage.get("lastDamageSource")),
                    time_since_last_damage_seconds=float(recent_damage["timeSinceLastDamageSeconds"]),
                ),
            ),
            loadout=CombatLoadoutState(
                held_item=ItemState.model_validate(player["heldItem"]),
                armor=ArmorState(
                    head=_item_or_none(armor.get("head")),
                    body=_item_or_none(armor.get("body")),
                    legs=_item_or_none(armor.get("legs")),
                ),
                accessories=[ItemState.model_validate(item) for item in _list(inventory, "accessories")],
            ),
            healing=HealingState(
                total_healing_item_count=int(healing["totalHealingItemCount"]),
                best_healing_item=_item_or_none(healing.get("bestHealingItem")),
                best_healing_amount=int(healing["bestHealingAmount"]),
            ),
            scene=_current_scene(snapshot),
            progression_stage=current_stage_id(snapshot),
        ),
    )


def project_exploration_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> ExplorationCapsule:
    current_scene = _scene_from_context(context) or _current_scene(snapshot)
    if event.event_type in {
        GameEventType.SCENE_FEATURE_ENTERED,
        GameEventType.SCENE_FEATURE_EXITED,
    }:
        data = SceneFeatureExplorationData(
            feature_category=event.subject_id,
            feature_name=event.subject_name,
            current_scene=current_scene,
            progression_stage=current_stage_id(snapshot),
            is_first_world_discovery=(
                event.event_type is GameEventType.SCENE_FEATURE_ENTERED
            ),
        )
        entity = _event_entity(event, "scene_feature")
    else:
        cell = AreaCell(x=event.cell_x, y=event.cell_y) if event.cell_x is not None and event.cell_y is not None else None
        data = AreaExplorationData(
            cell=cell,
            previous_scene=_previous_scene(context),
            current_scene=current_scene,
            progression_stage=current_stage_id(snapshot),
        )
        entity = None
    return ExplorationCapsule(
        capsule_type=CapsuleType.EXPLORATION,
        captured_at=captured_at,
        snapshot_tick=snapshot.tick,
        source_event_type=event.event_type.value,
        primary_entity=entity,
        data=data,
    )


def project_world_event_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> WorldEventCapsule:
    return WorldEventCapsule(
        capsule_type=CapsuleType.WORLD_EVENT,
        captured_at=captured_at,
        snapshot_tick=snapshot.tick,
        source_event_type=event.event_type.value,
        primary_entity=_event_entity(event, "world_event"),
        data=WorldEventCapsuleData(
            event_id=event.subject_id,
            event_name=event.subject_name,
            remaining_active_event_ids=(
                context.active_events
                if context and context.active_events is not None
                else [
                    str(item["id"])
                    for item in _list(snapshot.world, "activeEvents")
                    if isinstance(item, Mapping) and "id" in item
                ]
            ),
        ),
    )


def project_progress_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> ProgressCapsule:
    category = _progress_category(event.subject_id)
    entity_type = "boss" if category == "boss" else "world_milestone"
    entity = CapsuleEntityRef(entity_type=entity_type, entity_name=event.subject_name) if event.subject_name else None
    return ProgressCapsule(
        capsule_type=CapsuleType.PROGRESS,
        captured_at=captured_at,
        snapshot_tick=snapshot.tick,
        source_event_type=event.event_type.value,
        primary_entity=entity,
        data=ProgressCapsuleData(
            change_category=category,
            change_id=event.subject_id,
            change_name=event.subject_name,
            before=ProgressUnlockState(unlocked=False),
            after=ProgressUnlockState(unlocked=True),
            progression_stage_after=current_stage_id(snapshot),
            scene=SceneState(
                biomes=context.biomes if context and context.biomes is not None else _list(snapshot.scene, "biomes"),
                layer=_optional_string(snapshot.scene.get("layer")),
            ),
        ),
    )


def project_equipment_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> EquipmentCapsule:
    armor_before = context.armor_before if context else None
    armor_after = context.armor_after if context else None
    return EquipmentCapsule(
        capsule_type=CapsuleType.EQUIPMENT,
        captured_at=captured_at,
        snapshot_tick=snapshot.tick,
        source_event_type=event.event_type.value,
        primary_entity=None,
        data=EquipmentCapsuleData(
            armor_before=(
                ArmorState.model_validate(armor_before.model_dump(by_alias=True))
                if armor_before else None
            ),
            armor_after=(
                ArmorState.model_validate(armor_after.model_dump(by_alias=True))
                if armor_after else None
            ),
            accessories_added=[
                ItemState.model_validate(item.model_dump(by_alias=True))
                for item in ((context.accessories_added or []) if context else [])
            ],
            accessories_removed=[
                ItemState.model_validate(item.model_dump(by_alias=True))
                for item in ((context.accessories_removed or []) if context else [])
            ],
        ),
    )


def project_user_query_capsule(
    trigger: TriggerRequest,
) -> ConversationCapsule:
    snapshot = trigger.game_snapshot
    return _conversation_capsule(
        trigger=trigger,
        content=trigger.user_query,
        role="player",
        execution=None,
        snapshot=snapshot,
    )


def project_agent_response_capsule(
    trigger: TriggerRequest,
    execution: AgentExecutionResult,
) -> ConversationCapsule:
    return _conversation_capsule(
        trigger=trigger,
        content=execution.message,
        role="agent",
        execution=execution,
        snapshot=trigger.game_snapshot,
    )


def _conversation_capsule(
    *,
    trigger: TriggerRequest,
    content: str,
    role: str,
    execution: AgentExecutionResult | None,
    snapshot: GameSnapshot,
) -> ConversationCapsule:
    combat = snapshot.combat
    return ConversationCapsule(
        capsule_type=CapsuleType.CONVERSATION,
        captured_at=trigger.timestamp,
        snapshot_tick=snapshot.tick,
        source_event_type="USER_QUERY" if role == "player" else "AGENT_RESPONSE",
        primary_entity=None,
        data=ConversationCapsuleData(
            role=role,
            content=content,
            progression_stage=current_stage_id(snapshot),
            in_combat=bool(combat["inCombat"]),
            active_bosses=[
                BossState.model_validate(item)
                for item in _list(combat, "activeBosses")
            ],
            scene=_current_scene(snapshot),
            decision_action=execution.decision_action if execution else None,
            reasoning_rounds=execution.reasoning_rounds if execution else 0,
            used_game_context=(
                _project_used_game_context(execution.used_game_context)
                if execution else {}
            ),
            tool_history=execution.tool_history if execution else [],
        ),
    )


def _project_used_game_context(
    used_context: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            field: result[field]
            for field in CONVERSATION_CONTEXT_FIELDS[name]
            if field in result
        }
        for name, result in used_context.items()
        if name in CONVERSATION_CONTEXT_FIELDS
    }


def _event_entity(event: GameEventRequest, entity_type: str) -> CapsuleEntityRef | None:
    if event.subject_id is None and event.subject_name is None:
        return None
    return CapsuleEntityRef(entity_type=entity_type, entity_id=event.subject_id, entity_name=event.subject_name)


def _progress_category(value: str | None) -> str | None:
    if value and value.startswith("Boss:"):
        return "boss"
    if value in WORLD_MILESTONE_IDS:
        return "world_milestone"
    return None


def _current_scene(snapshot: GameSnapshot) -> SceneState:
    return SceneState(
        biomes=_list(snapshot.scene, "biomes"),
        layer=_optional_string(snapshot.scene.get("layer")),
        mini_biomes=_list(snapshot.scene, "miniBiomes"),
        special_areas=_list(snapshot.scene, "specialAreas"),
    )


def _scene_from_context(context: EventContext | None) -> SceneState | None:
    if context is None or all(value is None for value in (context.biomes, context.layer, context.mini_biomes, context.special_areas)):
        return None
    return SceneState(
        biomes=context.biomes or [],
        layer=context.layer,
        mini_biomes=context.mini_biomes or [],
        special_areas=context.special_areas or [],
    )


def _previous_scene(context: EventContext | None) -> SceneState | None:
    if context is None or all(value is None for value in (context.previous_biomes, context.previous_layer, context.previous_mini_biomes, context.previous_special_areas)):
        return None
    return SceneState(
        biomes=context.previous_biomes or [],
        layer=context.previous_layer,
        mini_biomes=context.previous_mini_biomes or [],
        special_areas=context.previous_special_areas or [],
    )


def _mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} 必须是 object")
    return value


def _list(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key, [])
    return list(value) if isinstance(value, (list, tuple)) else []


def _item_or_none(value: object) -> ItemState | None:
    return ItemState.model_validate(value) if isinstance(value, Mapping) else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
