"""Chat message schemas."""

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: str
    case_id: str
    role: str
    agent_name: str | None
    content: str
    metadata_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
