from sqlalchemy import and_
from sqlalchemy.orm import Session
from models import Message


def create_message(
    db: Session, *, user_id: int, chat_session_id: int, content: str, is_user: bool
) -> Message:

    db_message = Message(
        owner_id=user_id,
        chat_session_id=chat_session_id,
        content=content,
        is_user=is_user,
    )

    db.add(db_message)

    db.commit()

    db.refresh(db_message)

    return db_message


def get_messages(
    db: Session, *, user_id: int, chat_session_id: int, limit: int, offset: int = 0
) -> list[type[Message]]:

    return (
        db.query(Message)
        .filter(Message.owner_id == user_id, Message.chat_session_id == chat_session_id)
        .order_by(Message.timestamp.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_context_messages(
    db: Session, *, user_id: int, chat_session_id: int, limit: int
) -> list[type[Message]]:

    messages = (
        db.query(Message)
        .filter(
            and_(
                Message.owner_id == user_id, Message.chat_session_id == chat_session_id
            )
        )
        .order_by(Message.timestamp.desc())
        .limit(limit)
        .all()
    )

    return messages[::-1]


def update_message(
    db: Session, *, message_id: int, user_id: int, content: str
) -> type[Message] | None:

    db_message = db.query(Message).filter(Message.id == message_id).first()

    if not db_message:
        return None

    if db_message.owner_id != user_id:
        return None

    db_message.content = content

    db.commit()

    db.refresh(db_message)

    return db_message


def delete_message(db: Session, *, message_id: int, user_id: int) -> bool:

    db_message = db.query(Message).filter(Message.id == message_id).first()

    if not db_message:
        return False

    if db_message.owner_id != user_id:
        return False

    db.delete(db_message)

    db.commit()
    return True


def enforce_message_retention(
    db: Session, *, user_id: int, chat_session_id: int, limit: int
):

    count = (
        db.query(Message)
        .filter(Message.owner_id == user_id, Message.chat_session_id == chat_session_id)
        .count()
    )

    if count > limit:
        num_to_delete = count - limit

        oldest_messages = (
            db.query(Message.id)
            .filter(
                Message.owner_id == user_id, Message.chat_session_id == chat_session_id
            )
            .order_by(Message.timestamp.asc(), Message.id.asc())
            .limit(num_to_delete)
            .all()
        )

        ids_to_delete = [m.id for m in oldest_messages]

        if ids_to_delete:
            db.query(Message).filter(Message.id.in_(ids_to_delete)).delete(
                synchronize_session=False
            )
            db.commit()
