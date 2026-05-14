import uuid

import httpx
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import message_to_dict

from .models import DataPart, Message, Task, TaskSendRequest


class A2AClient:
    def __init__(self, base_url: str):
        # base_url: 에이전트 prefix까지 포함 (e.g. "http://localhost:8005/a2a/recommend-product")
        self.base_url = base_url.rstrip("/")

    async def send_task(self, session_id: str, data: dict) -> Task:
        serialized = {
            k: [message_to_dict(m) if isinstance(m, BaseMessage) else m for m in v]
               if isinstance(v, list) and v and isinstance(v[0], BaseMessage)
               else v
            for k, v in data.items()
            if v is not None
        }
        req = TaskSendRequest(
            id=str(uuid.uuid4()),
            sessionId=session_id,
            message=Message(role="user", parts=[DataPart(data=serialized)]),
        )
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                f"{self.base_url}/tasks/send",
                json=req.model_dump(),
            )
            resp.raise_for_status()
        return Task(**resp.json())
