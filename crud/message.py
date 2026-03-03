from sqlalchemy import and_
from sqlalchemy.orm import Session
from models import Message


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
) -> list[type[Message]]:
    # Retrieve messages for the specified user and chat session, ordered by timestamp, with pagination
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
    # Retrieve the most recent messages for the specified user and chat session, ordered by timestamp, with a limit on the number of messages returned
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
    # Return the messages in reverse order (oldest to newest) to maintain the original chronological order
    return messages[::-1]


# Retrieve the message to be updated from the database
def update_message(
    db: Session, *, message_id: int, user_id: int, content: str
) -> type[Message] | None:
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


def enforce_message_retention(
    db: Session, *, user_id: int, chat_session_id: int, limit: int
):
    # Count the total number of messages for the user and chat session
    count = (
        db.query(Message)
        .filter(Message.owner_id == user_id, Message.chat_session_id == chat_session_id)
        .count()
    )

    # If the count exceeds the limit, delete the oldest messages to enforce retention
    if count > limit:
        # Calculate how many messages need to be deleted to enforce the retention limit
        num_to_delete = count - limit

        # Retrieve the IDs of the oldest messages that need to be deleted, ordered by timestamp and ID to ensure consistent deletion
        oldest_messages = (
            db.query(Message.id)
            .filter(
                Message.owner_id == user_id, Message.chat_session_id == chat_session_id
            )
            .order_by(Message.timestamp.asc(), Message.id.asc())
            .limit(num_to_delete)
            .all()
        )

        # Extract the message IDs from the query result to perform a bulk delete
        ids_to_delete = [m.id for m in oldest_messages]

        # If there are messages to delete, perform a bulk delete operation to remove them from the database
        if ids_to_delete:
            db.query(Message).filter(Message.id.in_(ids_to_delete)).delete(
                synchronize_session=False
            )
            db.commit()
