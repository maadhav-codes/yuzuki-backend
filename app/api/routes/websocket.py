import asyncio
import time

from fastapi import APIRouter, Query, WebSocket
from fastapi.websockets import WebSocketDisconnect

from app.api.common import (
    MESSAGE_CONTEXT_LIMIT,
    MESSAGE_RETENTION_LIMIT,
    connection_manager,
    get_or_create_latest_session,
    logger,
    ollama_service,
    rate_limiter,
)
from app.core.auth import get_user_from_token
from app.crud import message as crud_message
from app.db.database import get_db
from app.models.models import ChatSession
from app.services.ollama_service import OllamaServiceError

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/chat")
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
