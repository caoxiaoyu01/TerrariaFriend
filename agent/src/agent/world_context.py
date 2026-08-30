from contextvars import ContextVar


current_world_id: ContextVar[str | None] = ContextVar(
    "current_world_id",
    default=None,
)


def require_current_world_id() -> str:
    world_id = current_world_id.get()
    if not world_id:
        raise RuntimeError("当前请求缺少世界身份")
    return world_id
