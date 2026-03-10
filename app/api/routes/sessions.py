from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.common import get_or_create_latest_session
from auth import get_current_user
from database import get_db
from models import ChatSession, User
from schemas import ChatSessionRead

router = APIRouter(tags=["sessions"])


@router.post(
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


@router.get("/sessions/current", response_model=ChatSessionRead)
def get_current_chat_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_or_create_latest_session(db, user_id=current_user.id)
