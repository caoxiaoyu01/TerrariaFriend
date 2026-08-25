from typing import Any

from agent.models.trigger_base import CamelModel


# Snapshot 的各个 section 保持 C# 原始 JSON 结构并作为 Tool 数据源
class GameSnapshot(CamelModel):
    tick: int
    player: dict[str, Any]
    inventory: dict[str, Any]
    world: dict[str, Any]
    progress: dict[str, Any]
    scene: dict[str, Any]
    combat: dict[str, Any]
    npc: dict[str, Any]
