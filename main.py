from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.messages import router as messages_router
from app.api.routes.root import router as root_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.voice import router as voice_router
from app.api.routes.websocket import router as websocket_router
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.settings import get_settings
from app.db.database import Base, engine

_ = get_settings()
configure_logging()

app = FastAPI(title="Yuzuki API")
app.add_middleware(RequestLoggingMiddleware)

API_V1_PREFIX = "/api/v1"

app.include_router(root_router, prefix=API_V1_PREFIX)
app.include_router(sessions_router, prefix=API_V1_PREFIX)
app.include_router(chat_router, prefix=API_V1_PREFIX)
app.include_router(messages_router, prefix=API_V1_PREFIX)
app.include_router(voice_router, prefix=API_V1_PREFIX)
app.include_router(websocket_router, prefix=API_V1_PREFIX)

Base.metadata.create_all(bind=engine)
