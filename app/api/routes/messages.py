from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.common import MESSAGE_CONTEXT_LIMIT, MESSAGE_RETENTION_LIMIT
from auth import get_current_user
from crud import message as crud_message
from database import get_db
from models import ChatSession, Message, User
from schemas import MessageCreate, MessageRead, MessageUpdate

router = APIRouter(tags=["messages"])


@router.post(
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


@router.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
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


@router.patch("/messages/{message_id}", response_model=MessageRead)
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


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
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
