from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.messages import router as messages_router
from app.api.routes.root import router as root_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.voice import router as voice_router
from app.api.routes.websocket import router as websocket_router
from database import Base, engine

app = FastAPI(title="Yuzuki API")

app.include_router(root_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(messages_router)
app.include_router(voice_router)
app.include_router(websocket_router)

Base.metadata.create_all(bind=engine)
