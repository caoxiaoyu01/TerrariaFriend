from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelModel(BaseModel):
    # 对齐 C# JsonNamingPolicy.CamelCase
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
