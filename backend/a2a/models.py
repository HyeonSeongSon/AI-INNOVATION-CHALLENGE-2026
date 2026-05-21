from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class DataPart(BaseModel):
    type: Literal["data"] = "data"
    data: Dict[str, Any]


Part = Annotated[Union[TextPart, DataPart], Field(discriminator="type")]


class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: List[Part]


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    skills: List[AgentSkill]
    inputModes: List[str] = ["data"]
    outputModes: List[str] = ["data"]


class TaskSendRequest(BaseModel):
    id: str
    sessionId: Optional[str] = None
    message: Message


class Task(BaseModel):
    id: str
    sessionId: Optional[str] = None
    status: TaskStatus
    artifacts: List[Dict[str, Any]] = []
    history: List[Message] = []
