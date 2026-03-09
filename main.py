import os
import time
import logging
from collections import defaultdict, deque
from typing import AsyncIterator, List
import asyncio

from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, status
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import get_current_user, get_user_from_token
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
logger = logging.getLogger(__name__)

MESSAGE_CONTEXT_LIMIT = int(os.getenv("MESSAGE_CONTEXT_LIMIT", "10"))

MESSAGE_RETENTION_LIMIT = int(os.getenv("MESSAGE_RETENTION_LIMIT", "200"))
WS_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("WS_RATE_LIMIT_WINDOW_SECONDS", "60"))
WS_RATE_LIMIT_MAX_MESSAGES = int(os.getenv("WS_RATE_LIMIT_MAX_MESSAGES", "20"))

ollama_service = OllamaService()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, connection_key: str, websocket: WebSocket) -> None:
        existing = self.active_connections.get(connection_key)
        if existing:
            await existing.close(code=4000, reason="Replaced by newer connection")
        await websocket.accept()
        self.active_connections[connection_key] = websocket

    def disconnect(self, connection_key: str, websocket: WebSocket) -> None:
        current = self.active_connections.get(connection_key)
        if current is websocket:
            self.active_connections.pop(connection_key, None)

    async def send_json(
        self, connection_key: str, payload: dict[str, str | int | bool]
    ) -> None:
        websocket = self.active_connections.get(connection_key)
        if websocket is not None:
            await websocket.send_json(payload)


class UserRateLimiter:
    def __init__(self, *, max_messages: int, window_seconds: int) -> None:
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        timestamps = self.events[user_id]
        cutoff = now - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= self.max_messages:
            return False
        timestamps.append(now)
        return True


connection_manager = ConnectionManager()
rate_limiter = UserRateLimiter(
    max_messages=WS_RATE_LIMIT_MAX_MESSAGES,
    window_seconds=WS_RATE_LIMIT_WINDOW_SECONDS,
)


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


@app.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    session_id: int | None = Query(default=None, ge=1),
    conversation_id: int | None = Query(default=None, ge=1),
    token: str | None = Query(default=None),
):
    db = next(get_db())
    start_time = time.perf_counter()
    conn_key: str | None = None
    user_id: int | None = None
    session: ChatSession | None = None
    received_count = 0
    current_stream_task: asyncio.Task | None = None

    try:
        bearer_header = websocket.headers.get("authorization", "")
        if not token and bearer_header.lower().startswith("bearer "):
            token = bearer_header[7:].strip()

        if not token:
            await websocket.close(code=4401, reason="Missing auth token")
            return

        current_user = get_user_from_token(token, db)
        user_id = current_user.id
        resolved_session_id = conversation_id or session_id

        if resolved_session_id is None:
            session = get_or_create_latest_session(db, user_id=current_user.id)
        else:
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == resolved_session_id,
                    ChatSession.owner_id == current_user.id,
                )
                .first()
            )
            if not session:
                await websocket.close(code=4404, reason="Chat session not found")
                return

        conn_key = f"{current_user.id}:{session.id}"
        await connection_manager.connect(conn_key, websocket)
        logger.info("ws_open user_id=%s session_id=%s", current_user.id, session.id)
        await connection_manager.send_json(
            conn_key, {"type": "connected", "session_id": session.id}
        )

        # Inner streaming task (can be cancelled)
        async def process_stream(user_msg_id: int, history: list, message_text: str):
            assistant_chunks: list[str] = []
            try:
                async for chunk in ollama_service.stream_chat(
                    history=history, message=message_text
                ):
                    assistant_chunks.append(chunk)
                    await connection_manager.send_json(
                        conn_key,
                        {
                            "type": "chunk",
                            "content": chunk,
                            "session_id": session.id,
                            "user_message_id": user_msg_id,
                        },
                    )
            except asyncio.CancelledError:
                partial_text = "".join(assistant_chunks).strip()
                if partial_text:
                    crud_message.create_message(
                        db,
                        user_id=current_user.id,
                        chat_session_id=session.id,
                        content=partial_text,
                        is_user=False,
                    )
                crud_message.enforce_message_retention(
                    db,
                    user_id=current_user.id,
                    chat_session_id=session.id,
                    limit=MESSAGE_RETENTION_LIMIT,
                )
                await connection_manager.send_json(
                    conn_key, {"type": "cancelled", "session_id": session.id}
                )
                raise
            except OllamaServiceError as exc:
                partial_text = "".join(assistant_chunks).strip()
                if partial_text:
                    crud_message.create_message(
                        db,
                        user_id=current_user.id,
                        chat_session_id=session.id,
                        content=partial_text,
                        is_user=False,
                    )
                crud_message.enforce_message_retention(
                    db,
                    user_id=current_user.id,
                    chat_session_id=session.id,
                    limit=MESSAGE_RETENTION_LIMIT,
                )
                await connection_manager.send_json(
                    conn_key,
                    {"type": "error", "error": str(exc), "session_id": session.id},
                )
                return

            assistant_text = "".join(assistant_chunks).strip()
            assistant_msg_id: int | None = None
            if assistant_text:
                assistant_msg = crud_message.create_message(
                    db,
                    user_id=current_user.id,
                    chat_session_id=session.id,
                    content=assistant_text,
                    is_user=False,
                )
                assistant_msg_id = assistant_msg.id

            crud_message.enforce_message_retention(
                db,
                user_id=current_user.id,
                chat_session_id=session.id,
                limit=MESSAGE_RETENTION_LIMIT,
            )

            await connection_manager.send_json(
                conn_key,
                {
                    "type": "done",
                    "session_id": session.id,
                    "message_id": assistant_msg_id or 0,
                },
            )

        while True:
            data = await websocket.receive_json()
            msg_type = str(data.get("type", "message")).strip().lower()

            if msg_type == "ping":
                await connection_manager.send_json(
                    conn_key, {"type": "pong", "timestamp": int(time.time())}
                )
                continue

            if msg_type == "cancel":
                if current_stream_task and not current_stream_task.done():
                    current_stream_task.cancel()
                continue

            if msg_type != "message":
                await connection_manager.send_json(
                    conn_key, {"type": "error", "error": "Unsupported message type"}
                )
                continue

            if not rate_limiter.allow(current_user.id):
                await connection_manager.send_json(
                    conn_key, {"type": "error", "error": "Rate limit exceeded"}
                )
                continue

            message_text = str(data.get("message", "")).strip()
            if not message_text:
                await connection_manager.send_json(
                    conn_key, {"type": "error", "error": "message cannot be blank"}
                )
                continue

            user_msg = crud_message.create_message(
                db,
                user_id=current_user.id,
                chat_session_id=session.id,
                content=message_text,
                is_user=True,
            )
            received_count += 1

            history = crud_message.get_context_messages(
                db,
                user_id=current_user.id,
                chat_session_id=session.id,
                limit=MESSAGE_CONTEXT_LIMIT,
            )

            if current_stream_task and not current_stream_task.done():
                current_stream_task.cancel()

            current_stream_task = asyncio.create_task(
                process_stream(user_msg.id, history, message_text)
            )

    except WebSocketDisconnect:
        logger.info(
            "ws_disconnect user_id=%s session_id=%s messages=%s duration_ms=%.2f",
            user_id,
            getattr(session, "id", None),
            received_count,
            (time.perf_counter() - start_time) * 1000,
        )
    except Exception:
        logger.exception(
            "ws_unexpected_error user_id=%s session_id=%s",
            user_id,
            getattr(session, "id", None),
        )
        if conn_key:
            try:
                await connection_manager.send_json(
                    conn_key, {"type": "error", "error": "Unexpected server error"}
                )
            except Exception:
                pass
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
    finally:
        if current_stream_task and not current_stream_task.done():
            current_stream_task.cancel()
        if conn_key:
            connection_manager.disconnect(conn_key, websocket)
        db.close()


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
