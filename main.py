from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, Base, engine
from models import ChatSession, Message, User
from schemas import MessageCreate, MessageUpdate, MessageRead
from crud import message as crud_message

# Create a FastAPI instance
app = FastAPI(title="Yuzuki API")


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


# --- Message CRUD Endpoints ---


# Endpoint to create a new message in a chat session
@app.post(
    "/sessions/{session_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session_message(
    session_id: int,
    message_in: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify session ownership before creating a message
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id)
        .first()
    )

    # Check if the chat session exists and belongs to the current user
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return crud_message.create_message(
        db,
        user_id=current_user.id,
        chat_session_id=session_id,
        content=message_in.content,
        is_user=message_in.is_user,
    )


# Endpoint to retrieve messages for a specific chat session with pagination
@app.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
def read_session_messages(
    session_id: int,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check if the chat session exists and belongs to the current user
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id)
        .first()
    )

    # 404 if session doesn't exist or doesn't belong to user
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Return the list of messages for the specified chat session with pagination
    messages = crud_message.get_messages(
        db,
        user_id=current_user.id,
        chat_session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return messages


# Endpoint to update the content of a specific message
@app.patch("/messages/{message_id}", response_model=MessageRead)
def update_message_content(
    message_id: int,
    message_in: MessageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check if the message exists and belongs to the current user
    existing_msg = db.query(Message).filter(Message.id == message_id).first()

    # 404 if message doesn't exist
    if not existing_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # 403 if user is not the owner of the message
    if existing_msg.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to edit this message"
        )

    # Update the message content and return the updated message
    updated_msg = crud_message.update_message(
        db, message_id=message_id, user_id=current_user.id, content=message_in.content
    )
    return updated_msg


# Endpoint to delete a specific message
@app.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_by_id(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check if the message exists and belongs to the current user
    existing_msg = db.query(Message).filter(Message.id == message_id).first()

    # 404 if message doesn't exist
    if not existing_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # 403 if user is not the owner of the message
    if existing_msg.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message"
        )

    # Delete the message and return 204 No Content
    crud_message.delete_message(db, message_id=message_id, user_id=current_user.id)
    return None


# Create all database tables based on the defined models
Base.metadata.create_all(bind=engine)
