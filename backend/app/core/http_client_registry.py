from typing import Any

from app.core.logging import get_logger

_registry: list[Any] = []
_logger = get_logger("http_client_registry")


def register(instance: Any) -> None:
    _registry.append(instance)


def replace(old_instance: Any, new_instance: Any) -> None:
    try:
        idx = _registry.index(old_instance)
        _registry[idx] = new_instance
    except ValueError:
        _registry.append(new_instance)


async def close_all() -> None:
    errors: list[tuple[str, str]] = []
    for instance in _registry:
        if not getattr(instance, "is_closed", False):
            try:
                await instance.aclose()
            except Exception as e:
                errors.append((type(instance).__name__, type(e).__name__))
    _registry.clear()
    if errors:
        _logger.warning("close_all_partial_failure", failures=errors)
