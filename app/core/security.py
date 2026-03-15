import re
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request, status
from jose import jwt
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.settings import get_settings

settings = get_settings()

API_CSP = "; ".join(
    [
        "default-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'none'",
    ]
)


class PostRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


post_rate_limiter = PostRateLimiter(
    limit=settings.http_post_rate_limit_max_requests,
    window_seconds=settings.http_post_rate_limit_window_seconds,
)


def _client_key_from_request(request: Request) -> str:
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        try:
            claims = jwt.get_unverified_claims(token)
            subject = str(claims.get("sub", "")).strip()
            if subject:
                return f"user:{subject}"
        except Exception:
            pass

    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return f"ip:{first_hop}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class SecurityHeadersAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() == "POST":
            key = _client_key_from_request(request)
            if not post_rate_limiter.allow(key):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Please retry later."},
                )

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = API_CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text_input(value: str) -> str:
    sanitized = _CONTROL_CHARS_RE.sub("", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized
