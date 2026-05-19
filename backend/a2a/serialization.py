from langchain_core.messages import BaseMessage, messages_from_dict


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "data": m.model_dump()} for m in messages]


def deserialize_messages(raw: list[dict]) -> list[BaseMessage]:
    return messages_from_dict(raw)
