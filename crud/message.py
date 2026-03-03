from sqlalchemy.orm import Session
from models import Message
from typing import List, Optional


# Create a new message in the database
def create_message(
    db: Session, *, user_id: int, chat_session_id: int, content: str, is_user: bool
) -> Message:
    # Create a new Message instance with the provided parameters
    db_message = Message(
        owner_id=user_id,
        chat_session_id=chat_session_id,
        content=content,
        is_user=is_user,
    )
    # Add the new message to the database session
    db.add(db_message)
    # Commit the transaction to save the new message in the database
    db.commit()
    # Refresh the instance to get the updated state from the database
    db.refresh(db_message)
    # Return the newly created message instance
    return db_message


# Retrieve messages for a specific user and chat session with pagination
def get_messages(
    db: Session, *, user_id: int, chat_session_id: int, limit: int, offset: int = 0
) -> List[Message]:
    # Retrieve messages for the specified user and chat session, ordered by timestamp, with pagination
    return (
        db.query(Message)
        .filter(Message.owner_id == user_id, Message.chat_session_id == chat_session_id)
        .order_by(Message.timestamp.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# Retrieve the message to be updated from the database
def update_message(
    db: Session, *, message_id: int, user_id: int, content: str
) -> Optional[Message]:
    # Retrieve the message to be updated from the database using its ID
    db_message = db.query(Message).filter(Message.id == message_id).first()

    # If the message does not exist, return None
    if not db_message:
        return None

    # Check if the user is the owner of the message; if not, return None
    if db_message.owner_id != user_id:
        return None

    # Update the content of the message with the new content provided
    db_message.content = content
    # Commit the transaction to save the updated message in the database
    db.commit()
    # Refresh the instance to get the updated state from the database
    db.refresh(db_message)
    # Return the updated message instance
    return db_message


# Delete a message from the database if the user is the owner
def delete_message(db: Session, *, message_id: int, user_id: int) -> bool:
    # Retrieve the message to be deleted from the database using its ID
    db_message = db.query(Message).filter(Message.id == message_id).first()

    # If the message does not exist, return False
    if not db_message:
        return False

    # Check if the user is the owner of the message; if not, return False
    if db_message.owner_id != user_id:
        return False

    # Delete the message from the database session
    db.delete(db_message)
    # Commit the transaction to save the changes in the database
    db.commit()
    return True
