from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.common import (
    MESSAGE_CONTEXT_LIMIT,
    MESSAGE_RETENTION_LIMIT,
    get_or_create_latest_session,
    ollama_service,
)
from app.core.auth import get_current_user
from app.crud import message as crud_message
from app.db.database import get_db
from app.models.models import ChatSession, User
from app.services.ollama_service import OllamaServiceError
from app.schemas.schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
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
