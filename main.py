import os
from typing import AsyncIterator, List


from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, Base, engine
from models import ChatSession, Message, User
from ollama_service import OllamaService, OllamaServiceError
from schemas import (
    ChatRequest,
    ChatSessionRead,
    MessageCreate,
    MessageUpdate,
    MessageRead,
)
from crud import message as crud_message

app = FastAPI(title="Yuzuki API")  # Set the title of the API for documentation purposes

MESSAGE_CONTEXT_LIMIT = int(
    os.getenv("MESSAGE_CONTEXT_LIMIT", "10")
)  # Maximum number of recent messages to include as context for the Ollama model, configurable via environment variable with a default of 10

MESSAGE_RETENTION_LIMIT = int(
    os.getenv("MESSAGE_RETENTION_LIMIT", "200")
)  # Maximum number of messages to retain in the database for a chat session, configurable via environment variable with a default of 200; older messages will be deleted to enforce this limit

ollama_service = (
    OllamaService()
)  # Initialize the OllamaService to interact with the Ollama API for generating chat responses


# Helper function to get the latest chat session for a user or create a new one if none exists
def get_or_create_latest_session(
    db: Session, user_id: int
) -> type[ChatSession] | ChatSession:
    # Try to find the most recent chat session for the user, ordered by creation time and ID
    session = (
        db.query(ChatSession)
        .filter(ChatSession.owner_id == user_id)
        .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        .first()
    )
    # If a session exists, return it; otherwise, create a new session for the user
    if session:
        return session

    session = ChatSession(owner_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


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


# Endpoint to create a new chat session for the authenticated user
@app.post(
    "/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED
)
def create_chat_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(owner_id=current_user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# Endpoint to retrieve the most recent chat session for the authenticated user, or create one if it doesn't exist
@app.get("/sessions/current", response_model=ChatSessionRead)
def get_current_chat_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_or_create_latest_session(db, user_id=current_user.id)


# Endpoint to handle chat interactions with the Ollama API, including streaming responses and managing chat history
@app.post("/chat")
async def chat_with_ollama(
    chat_in: ChatRequest,
    session_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # If a session_id is provided, verify that it exists and belongs to the current user; otherwise, get or create the latest session for the user
    if session_id is not None:
        session = (
            db.query(ChatSession)
            .filter(
                ChatSession.id == session_id, ChatSession.owner_id == current_user.id
            )
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        session = get_or_create_latest_session(db, user_id=current_user.id)

    # Retrieve the recent chat history for the session to provide context for the Ollama model, limited by MESSAGE_CONTEXT_LIMIT
    context_messages = crud_message.get_context_messages(
        db,
        user_id=current_user.id,
        chat_session_id=session.id,
        limit=MESSAGE_CONTEXT_LIMIT,
    )

    # Create a new message in the database for the user's input before streaming the response from the Ollama model
    crud_message.create_message(
        db,
        user_id=current_user.id,
        chat_session_id=session.id,
        content=chat_in.message,
        is_user=True,
    )

    # Stream the response from the Ollama model based on the provided chat history and user message, and handle any errors that may occur during the streaming process
    model_stream = ollama_service.stream_chat(
        history=context_messages, message=chat_in.message
    )
    assistant_chunks: list[str] = []

    # Attempt to get the first chunk of the response to handle any immediate errors from the Ollama API before starting the streaming response; if an error occurs, enforce message retention limits and return a 503 error
    try:
        first_chunk = await anext(model_stream)
    except StopAsyncIteration:
        first_chunk = ""
    except OllamaServiceError as exc:
        crud_message.enforce_message_retention(
            db,
            user_id=current_user.id,
            chat_session_id=session.id,
            limit=MESSAGE_RETENTION_LIMIT,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Define an asynchronous generator function to yield chunks of the assistant's response as they are received from the Ollama API, while also accumulating the full response text to save in the database once streaming is complete
    async def response_stream() -> AsyncIterator[str]:
        if first_chunk:
            assistant_chunks.append(first_chunk)
            yield first_chunk

        try:
            async for chunk in model_stream:
                assistant_chunks.append(chunk)
                yield chunk
        except OllamaServiceError:
            return
        finally:
            assistant_text = "".join(assistant_chunks).strip()
            if assistant_text:
                crud_message.create_message(
                    db,
                    user_id=current_user.id,
                    chat_session_id=session.id,
                    content=assistant_text,
                    is_user=False,
                )
            crud_message.enforce_message_retention(
                db,
                user_id=current_user.id,
                chat_session_id=session.id,
                limit=MESSAGE_RETENTION_LIMIT,
            )

    return StreamingResponse(response_stream(), media_type="text/plain")


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

    message = crud_message.create_message(
        db,
        user_id=current_user.id,
        chat_session_id=session_id,
        content=message_in.content,
        is_user=message_in.is_user,
    )
    crud_message.enforce_message_retention(
        db,
        user_id=current_user.id,
        chat_session_id=session_id,
        limit=MESSAGE_RETENTION_LIMIT,
    )
    return message


# Endpoint to retrieve messages for a specific chat session with pagination
@app.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
def read_session_messages(
    session_id: int,
    limit: int = Query(default=MESSAGE_CONTEXT_LIMIT, ge=1, le=MESSAGE_CONTEXT_LIMIT),
    offset: int = Query(default=0, ge=0),
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
