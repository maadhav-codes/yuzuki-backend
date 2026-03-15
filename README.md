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
DATABASE_URL=sqlite:///./yuzuki-ai.db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
MESSAGE_CONTEXT_LIMIT=10
MESSAGE_RETENTION_LIMIT=200
WS_RATE_LIMIT_WINDOW_SECONDS=60
WS_RATE_LIMIT_MAX_MESSAGES=20
HTTP_POST_RATE_LIMIT_WINDOW_SECONDS=60
HTTP_POST_RATE_LIMIT_MAX_REQUESTS=30
SECRETS_MAX_AGE_DAYS=90
SECRETS_LAST_ROTATED_AT=2026-03-01
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

- `GET /api/v1/` health message
- `GET /api/v1/health` DB connectivity check
- `POST /api/v1/sessions` create chat session
- `GET /api/v1/sessions/current` get latest or create one
- `POST /api/v1/chat` stream LLM response (HTTP stream)
- `POST /api/v1/sessions/{session_id}/messages` create message
- `GET /api/v1/sessions/{session_id}/messages` list messages
- `PATCH /api/v1/messages/{message_id}` update message
- `DELETE /api/v1/messages/{message_id}` delete message
- `POST /api/v1/voice/tts` placeholder TTS endpoint
- `GET /api/v1/voice/config` voice config endpoint
- `WS /api/v1/ws/chat` realtime chat (token required)

## Auth

Protected HTTP routes use bearer auth in `Authorization` header:

```text
Authorization: Bearer <supabase-jwt>
```

WebSocket auth supports:

- query param: `?token=<jwt>`
- or `Authorization: Bearer <jwt>` header

## Notes

- Database is configured through `DATABASE_URL`.
- Default is SQLite (`sqlite:///./yuzuki-ai.db`), but PostgreSQL can be used by setting `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname`.
- Tables are auto-created on app startup.
- LLM integration is isolated in `app/services/ollama_service.py` for easier mocking/testing.
- POST endpoints are rate-limited by a middleware bucket keyed by JWT subject (fallback: client IP).
- Request text fields are sanitized and validated with Pydantic validators before DB writes.
