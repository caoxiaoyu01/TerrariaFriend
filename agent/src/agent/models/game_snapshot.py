from typing import Any

from agent.models.trigger_base import CamelModel


# 保留游戏端传来的字段结构 供工具直接读取
class GameSnapshot(CamelModel):
    tick: int
    player: dict[str, Any]
    inventory: dict[str, Any]
    world: dict[str, Any]
    progress: dict[str, Any]
    scene: dict[str, Any]
    combat: dict[str, Any]
    npc: dict[str, Any]
