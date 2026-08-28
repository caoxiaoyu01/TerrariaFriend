from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelModel(BaseModel):
    # 字段名与游戏端发送的格式保持一致
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
