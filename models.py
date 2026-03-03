from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

# Define the base class for SQLAlchemy models, which will be used to create the database tables
Base = declarative_base()


# Define the User model, which represents a user in the system and their associated messages
class User(Base):
    __tablename__ = "users"

    # Unique identifier for the user, set as the primary key and indexed for faster queries
    id = Column(Integer, primary_key=True, index=True)

    # Unique identifier from Supabase, indexed for faster queries and cannot be null
    supabase_uid = Column(String, unique=True, index=True, nullable=False)

    # Email address of the user, must be unique and indexed for faster queries
    email = Column(String, unique=True, index=True)

    # Establishes a relationship to the Message model, allowing access to a user's messages via user.messages
    messages = relationship("Message", back_populates="owner")


# Define the Message model, which represents a message in the system and its relationship to a user
class Message(Base):
    __tablename__ = "messages"

    # Unique identifier for the message, set as the primary key and indexed for faster queries
    id = Column(Integer, primary_key=True, index=True)

    # Content of the message, cannot be null
    content = Column(String, nullable=False)

    # Indicates whether the message was sent by the user (True) or the system (False), defaults to True
    is_user = Column(Boolean, default=True)

    # Timestamp of when the message was created, defaults to the current UTC time
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Foreign key linking to the users table, indicating which user owns this message
    owner_id = Column(Integer, ForeignKey("users.id"))

    # Establishes a relationship to the User model, allowing access to the message's owner via message.owner
    owner = relationship("User", back_populates="messages")
