from typing import Any

_registry: list[Any] = []


def register(instance: Any) -> None:
    _registry.append(instance)


def replace(old_instance: Any, new_instance: Any) -> None:
    try:
        idx = _registry.index(old_instance)
        _registry[idx] = new_instance
    except ValueError:
        _registry.append(new_instance)


async def close_all() -> None:
    for instance in _registry:
        if not getattr(instance, "is_closed", False):
            await instance.aclose()
    _registry.clear()
