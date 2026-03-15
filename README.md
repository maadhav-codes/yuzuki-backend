# Yuzuki Backend

FastAPI backend for chat sessions, message history, and realtime websocket chat powered by Ollama.

## Project Structure

```text
.
├── app/
│   ├── api/
│   │   ├── common.py
│   │   └── routes/
│   │       ├── chat.py
│   │       ├── messages.py
│   │       ├── root.py
│   │       ├── sessions.py
│   │       ├── voice.py
│   │       └── websocket.py
│   ├── core/
│   │   ├── auth.py
│   │   └── dependencies.py
│   ├── crud/
│   │   └── message.py
│   ├── db/
│   │   └── database.py
│   ├── models/
│   │   └── models.py
│   ├── schemas/
│   │   └── schemas.py
│   └── services/
│       └── ollama_service.py
├── main.py
├── requirements.txt
└── yuzuki-ai.db
```

## Requirements

- Python 3.10+
- Ollama running locally (default `http://localhost:11434`)
- Supabase JWT configuration for auth

## Environment Variables

Create `.env` in project root:

```env
SUPABASE_URL=...
SUPABASE_JWKS_URL=...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
MESSAGE_CONTEXT_LIMIT=10
MESSAGE_RETENTION_LIMIT=200
WS_RATE_LIMIT_WINDOW_SECONDS=60
WS_RATE_LIMIT_MAX_MESSAGES=20
```

`SUPABASE_URL` and `SUPABASE_JWKS_URL` are required and now validated on startup via `pydantic-settings`.
If either is missing or invalid, the app fails fast with a clear validation error.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

Server starts at `http://127.0.0.1:8000`.

## API Overview

- `GET /` health message
- `GET /health` DB connectivity check
- `POST /sessions` create chat session
- `GET /sessions/current` get latest or create one
- `POST /chat` stream LLM response (HTTP stream)
- `POST /sessions/{session_id}/messages` create message
- `GET /sessions/{session_id}/messages` list messages
- `PATCH /messages/{message_id}` update message
- `DELETE /messages/{message_id}` delete message
- `POST /voice/tts` placeholder TTS endpoint
- `GET /voice/config` voice config endpoint
- `WS /ws/chat` realtime chat (token required)

## Auth

Protected HTTP routes use bearer auth in `Authorization` header:

```text
Authorization: Bearer <supabase-jwt>
```

WebSocket auth supports:

- query param: `?token=<jwt>`
- or `Authorization: Bearer <jwt>` header

## Notes

- SQLite is used by default (`yuzuki-ai.db`).
- Tables are auto-created on app startup.
- LLM integration is isolated in `app/services/ollama_service.py` for easier mocking/testing.
