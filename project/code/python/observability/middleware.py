"""请求 ID 中间件 + HTTP 指标。"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability.context import set_request_id
from observability.metrics import observe_http

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        set_request_id(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        except Exception:
            logger.exception(
                "unhandled_request_error",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            duration = time.perf_counter() - start
            observe_http(request.method, request.url.path, status, duration)
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
