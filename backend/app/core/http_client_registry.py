from typing import Any

_registry: list[Any] = []


def register(instance: Any) -> None:
    _registry.append(instance)


async def close_all() -> None:
    for instance in _registry:
        await instance.aclose()
    _registry.clear()
