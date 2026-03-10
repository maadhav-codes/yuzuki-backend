from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ChatSessionRead(BaseModel):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str
    is_user: bool = True


class MessageUpdate(BaseModel):
    content: str


class MessageRead(BaseModel):
    id: int
    content: str
    is_user: bool
    timestamp: datetime
    owner_id: int
    chat_session_id: int

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message cannot be blank")
        return cleaned


class VoiceTTSRequest(BaseModel):
    text: str
    voiceId: Optional[str] = None


class VoiceTTSResponse(BaseModel):
    success: bool
    audioUrl: Optional[str] = None
    note: str


class VoiceConfigResponse(BaseModel):
    supportedLanguages: list[str]
    defaultVoice: str
