from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    supabase_uid = Column(String, unique=True, index=True, nullable=False)

    email = Column(String, unique=True, index=True)

    chat_sessions = relationship("ChatSession", back_populates="owner")

    messages = relationship("Message", back_populates="owner")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="chat_sessions")

    messages = relationship("Message", back_populates="chat_session")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    content = Column(String, nullable=False)

    is_user = Column(Boolean, default=True)

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner_id = Column(Integer, ForeignKey("users.id"))

    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id"), index=True)

    owner = relationship("User", back_populates="messages")

    chat_session = relationship("ChatSession", back_populates="messages")
