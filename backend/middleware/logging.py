import uuid
import time
import logging
from contextvars import ContextVar

from pythonjsonlogger import json as jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Stamp request_id onto every LogRecord at creation time so all handlers —
# including dynamically added ones in tests — always see the attribute.
_orig_factory = logging.getLogRecordFactory()


def _request_id_factory(*args, **kwargs) -> logging.LogRecord:
    record = _orig_factory(*args, **kwargs)
    record.request_id = request_id_var.get("")  # type: ignore[attr-defined]
    return record


logging.setLogRecordFactory(_request_id_factory)


def setup_logging(log_level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = str(uuid.uuid4())
        request_id_var.set(rid)
        request.state.request_id = rid

        logger = logging.getLogger("api.request")
        start = time.perf_counter()
        logger.info("request_start", extra={"method": request.method, "path": str(request.url.path)})

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_end",
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-Id"] = rid
        return response
