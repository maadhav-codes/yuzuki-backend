from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# Schema for creating a new chat session
class ChatSessionRead(BaseModel):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Schema for creating a new message
class MessageCreate(BaseModel):
    content: str
    is_user: bool = True


# Schema for updating an existing message
class MessageUpdate(BaseModel):
    content: str


# Schema for reading a message from the database
class MessageRead(BaseModel):
    id: int
    content: str
    is_user: bool
    timestamp: datetime
    owner_id: int
    chat_session_id: int

    # This allows Pydantic to read data from ORM models directly
    class Config:
        from_attributes = True


# Schema for the chat request payload
class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1, max_length=4000
    )  # Added validation for message length

    @field_validator("message")
    @classmethod  # Added a validator to ensure the message is not blank or just whitespace
    def validate_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message cannot be blank")
        return cleaned
