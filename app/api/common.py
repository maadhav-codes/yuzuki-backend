import asyncio
import logging
import time
from collections import defaultdict, deque

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.models import ChatSession
from app.services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

settings = get_settings()
MESSAGE_CONTEXT_LIMIT = settings.message_context_limit
MESSAGE_RETENTION_LIMIT = settings.message_retention_limit
WS_RATE_LIMIT_WINDOW_SECONDS = settings.ws_rate_limit_window_seconds
WS_RATE_LIMIT_MAX_MESSAGES = settings.ws_rate_limit_max_messages

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
        self.lock = asyncio.Lock()

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
