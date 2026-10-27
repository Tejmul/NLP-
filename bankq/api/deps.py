"""Shared dependencies: API-key auth, rate limiting, database sessions and the router."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request, status

from ..config import get_settings
from ..db.session import session_scope


def get_router(request: Request):
    router = getattr(request.app.state, "router", None)
    if router is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No model loaded. Train one with: make train")
    return router


def get_db():
    with session_scope() as s:
        yield s


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Returns the caller identity. With no keys configured (local dev), everyone is 'dev'."""
    keys = get_settings().api_key_set
    if not keys:
        return "dev"
    if x_api_key not in keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key. Send it in the X-API-Key header.")
    return f"key:{x_api_key[:4]}…"


class SlidingWindowLimiter:
    """In-process limiter. For several API replicas, swap this for a Redis-backed limiter."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                retry = int(window - (now - q[0])) + 1
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded.",
                                    headers={"Retry-After": str(retry)})
            q.append(now)


limiter = SlidingWindowLimiter()


def rate_limited(request: Request, caller: str = Depends(require_api_key)) -> str:
    client = caller if caller != "dev" else (request.client.host if request.client else "local")
    limiter.check(client, get_settings().rate_limit_per_minute)
    return caller
