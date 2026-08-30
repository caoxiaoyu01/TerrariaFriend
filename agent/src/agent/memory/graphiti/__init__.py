from importlib import import_module


_EXPORTS = {
    "GraphitiMemoryBackend": ("agent.memory.graphiti.backend", "GraphitiMemoryBackend"),
    "GraphitiMemoryWriter": ("agent.memory.graphiti.writer", "GraphitiMemoryWriter"),
    "GraphitiSettings": ("agent.memory.graphiti.config", "GraphitiSettings"),
    "MemoryIngestionContext": ("agent.memory.graphiti.writer", "MemoryIngestionContext"),
    "MemoryWriteFailure": ("agent.memory.graphiti.writer", "MemoryWriteFailure"),
    "MemoryWriteReport": ("agent.memory.graphiti.writer", "MemoryWriteReport"),
    "create_graphiti": ("agent.memory.graphiti.client", "create_graphiti"),
}

__all__ = [
    "GraphitiMemoryBackend",
    "GraphitiMemoryWriter",
    "GraphitiSettings",
    "MemoryIngestionContext",
    "MemoryWriteFailure",
    "MemoryWriteReport",
    "create_graphiti",
]


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
