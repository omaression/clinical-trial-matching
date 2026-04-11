import math
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.api.errors import api_exception
from app.config import settings
from app.db.session import get_db

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_db_session(db: Session = Depends(get_db)):
    return db


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int | None]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            window = self._requests[key]
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - window[0])))
                return False, retry_after
            window.append(now)
        return True, None


def get_rate_limiter(request: Request) -> InMemoryRateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        limiter = InMemoryRateLimiter()
        request.app.state.rate_limiter = limiter
    return limiter


def require_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str:
    if api_key != settings.api_key:
        raise api_exception(401, "Valid X-API-Key header required")
    request.state.authenticated_api_key = api_key
    return api_key


def rate_limit_dependency(
    bucket: str,
    *,
    limit_setting: str,
    window_setting: str,
):
    def dependency(
        request: Request,
        api_key: str = Depends(require_api_key),
        limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
    ) -> str:
        limit = int(getattr(settings, limit_setting))
        window_seconds = int(getattr(settings, window_setting))
        client_host = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.allow(
            key=f"{bucket}:{client_host}:{api_key}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise api_exception(
                429,
                "Operational request rate limit exceeded",
                headers={"Retry-After": str(retry_after or 1)},
            )
        return api_key

    return dependency


def add_request_log_context(request: Request, **context: object) -> None:
    current = dict(getattr(request.state, "log_context", {}))
    current.update({key: value for key, value in context.items() if value is not None})
    request.state.log_context = current
