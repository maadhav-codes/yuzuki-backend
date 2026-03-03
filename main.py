from typing import List

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text, desc
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, Base, engine
from models import Message, User

# Create a FastAPI instance to define the API endpoints
app = FastAPI(title="Yuzuki API")


# Define the base model for incoming message data, which includes the content of the message and whether it was sent by the user
class MessageBase(BaseModel):
    content: str
    is_user: bool


# Define the response model for messages, which includes the message ID, content, whether it was sent by the user, and the timestamp
class MessageResponse(BaseModel):
    id: int
    content: str
    is_user: bool
    timestamp: str

    # This configuration allows the response model to be created from SQLAlchemy model instances directly
    class Config:
        from_attributes = True


# Helper function to retrieve the most recent messages for a user, limited to a specified number
def get_context_messages(db: Session, user_id: int, limit: int = 5):
    messages = (
        # Query the Message table in the database
        db.query(Message)
        # Filter messages to only include those that belong to the specified user
        .filter(Message.owner_id == user_id)
        # Order the messages by timestamp in descending order to get the most recent messages first
        .order_by(desc(Message.timestamp))
        # Limit the number of messages returned to the specified limit
        .limit(limit)
        # Retrieve all the messages that match the query criteria
        .all()
    )

    return messages[::-1]


# Endpoint to check if the backend is running
@app.get("/")
def read_root():
    return {"message": "Backend is running"}


# Health check endpoint to verify database connectivity
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {str(e)}")


@app.get("/messages/{user_id}", response_model=List[MessageResponse])
def get_user_messages(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # Ensure that users can only access their own messages
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Query the Message table to retrieve all messages that belong to the specified user ID
    messages = db.query(Message).filter(Message.owner_id == user_id).all()
    return messages


@app.post("/chat", response_model=MessageResponse)
def create_chat(
    message: MessageBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # Create a new Message instance for the user's message, setting the content, is_user flag to True, and linking it to the current user's ID
    user_message = Message(
        content=message.content, is_user=True, owner_id=current_user.id
    )
    # Add the new user message to the database session
    db.add(user_message)
    # Commit the transaction to save the user message in the database
    db.commit()

    # Retrieve the most recent messages for the current user to provide context for generating the AI response
    history = get_context_messages(db=db, user_id=current_user.id, limit=5)
    # Combine the content of the recent messages into a single string to use as context for generating the AI response
    context_text = " ".join([msg.content for msg in history])

    # Placeholder for AI response generation logic, currently just echoes the user's message
    ai_response_text = f"Echo: {message.content}"

    # Create a new Message instance for the AI response, setting the content, is_user flag to False, and linking it to the current user's ID
    ai_message = Message(
        content=ai_response_text, is_user=False, owner_id=current_user.id
    )
    # Add the new AI message to the database session
    db.add(ai_message)
    # Commit the transaction to save the AI message in the database
    db.commit()

    return ai_message


# Create the messages table in the database if it doesn't already exist
Base.metadata.create_all(bind=engine)
