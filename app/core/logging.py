import json
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logging.getLogger("request").exception(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "query": str(request.url.query),
                        "status_code": 500,
                        "duration_ms": elapsed_ms,
                        "client_ip": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent"),
                    }
                )
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["x-request-id"] = request_id
        logging.getLogger("request").info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "status_code": status_code,
                    "duration_ms": elapsed_ms,
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                }
            )
        )
        return response
