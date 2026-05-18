from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

_TYPE_MAP: dict[str, type[BaseMessage]] = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
    "tool": ToolMessage,
}


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "data": m.model_dump()} for m in messages]


def deserialize_messages(raw: list[dict]) -> list[BaseMessage]:
    result = []
    for item in raw:
        cls = _TYPE_MAP.get(item.get("type", ""))
        if cls is None:
            continue
        result.append(cls(**item.get("data", {})))
    return result
