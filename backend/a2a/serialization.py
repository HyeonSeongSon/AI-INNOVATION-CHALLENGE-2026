from langchain_core.messages import BaseMessage, messages_from_dict
from app.core.logging import get_logger

_logger = get_logger("a2a.serialization")


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "data": m.model_dump()} for m in messages]


def deserialize_messages(raw: list[dict]) -> list[BaseMessage]:
    try:
        return messages_from_dict(raw)
    except Exception as e:
        _logger.error("a2a_deserialize_failed", error_type=type(e).__name__, count=len(raw), exc_info=True)
        raise ValueError("A2A 메시지 역직렬화 실패") from None
