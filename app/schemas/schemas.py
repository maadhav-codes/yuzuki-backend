from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.security import sanitize_text_input


class ChatSessionRead(BaseModel):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    is_user: bool = True

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = sanitize_text_input(value)
        if not cleaned:
            raise ValueError("content cannot be blank")
        return cleaned


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = sanitize_text_input(value)
        if not cleaned:
            raise ValueError("content cannot be blank")
        return cleaned


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
        cleaned = sanitize_text_input(value)
        if not cleaned:
            raise ValueError("message cannot be blank")
        return cleaned


class VoiceTTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    emotion: str = Field(default="talking", max_length=60)
    speed: float = Field(default=0.95, ge=0.6, le=1.6)
    styleWeight: float = Field(default=1.0, ge=0.1, le=2.0)
    voiceId: Optional[str] = Field(default=None, max_length=120)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = sanitize_text_input(value)
        if not cleaned:
            raise ValueError("text cannot be blank")
        return cleaned

    @field_validator("voiceId")
    @classmethod
    def validate_voice_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = sanitize_text_input(value)
        return cleaned or None

    @field_validator("emotion")
    @classmethod
    def validate_emotion(cls, value: str) -> str:
        cleaned = sanitize_text_input(value)
        return cleaned or "talking"


class VoiceConfigResponse(BaseModel):
    supportedLanguages: list[str]
    defaultVoice: str
