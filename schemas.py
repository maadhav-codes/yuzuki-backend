from datetime import datetime
from pydantic import BaseModel


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
