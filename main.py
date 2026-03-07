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

app = FastAPI(title="Yuzuki API")

MESSAGE_CONTEXT_LIMIT = int(os.getenv("MESSAGE_CONTEXT_LIMIT", "10"))

MESSAGE_RETENTION_LIMIT = int(os.getenv("MESSAGE_RETENTION_LIMIT", "200"))

ollama_service = OllamaService()


def get_or_create_latest_session(
    db: Session, user_id: int
) -> type[ChatSession] | ChatSession:

    session = (
        db.query(ChatSession)
        .filter(ChatSession.owner_id == user_id)
        .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        .first()
    )

    if session:
        return session

    session = ChatSession(owner_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/")
def read_root():
    return {"message": "Backend is running"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {str(e)}")


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


@app.get("/sessions/current", response_model=ChatSessionRead)
def get_current_chat_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_or_create_latest_session(db, user_id=current_user.id)


@app.post("/chat")
async def chat_with_ollama(
    chat_in: ChatRequest,
    session_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

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

    context_messages = crud_message.get_context_messages(
        db,
        user_id=current_user.id,
        chat_session_id=session.id,
        limit=MESSAGE_CONTEXT_LIMIT,
    )

    crud_message.create_message(
        db,
        user_id=current_user.id,
        chat_session_id=session.id,
        content=chat_in.message,
        is_user=True,
    )

    model_stream = ollama_service.stream_chat(
        history=context_messages, message=chat_in.message
    )
    assistant_chunks: list[str] = []

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

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id)
        .first()
    )

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


@app.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
def read_session_messages(
    session_id: int,
    limit: int = Query(default=MESSAGE_CONTEXT_LIMIT, ge=1, le=MESSAGE_CONTEXT_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = crud_message.get_messages(
        db,
        user_id=current_user.id,
        chat_session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return messages


@app.patch("/messages/{message_id}", response_model=MessageRead)
def update_message_content(
    message_id: int,
    message_in: MessageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    existing_msg = db.query(Message).filter(Message.id == message_id).first()

    if not existing_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if existing_msg.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to edit this message"
        )

    updated_msg = crud_message.update_message(
        db, message_id=message_id, user_id=current_user.id, content=message_in.content
    )
    return updated_msg


@app.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_by_id(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    existing_msg = db.query(Message).filter(Message.id == message_id).first()

    if not existing_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if existing_msg.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message"
        )

    crud_message.delete_message(db, message_id=message_id, user_id=current_user.id)
    return None


Base.metadata.create_all(bind=engine)
