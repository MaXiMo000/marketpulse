"""Authentication, rate limiting and startup configuration checks."""
import hmac
import math
import time
from collections import deque

from fastapi import Depends, HTTPException, Request

from app.config import Settings, settings

MIN_TOKEN_LENGTH = 32


class RateLimiter:
    """Sliding-window counter per key, in process memory (one API worker)."""

    def __init__(self, limit: int, window_s: float, clock=time.monotonic, max_keys: int = 10_000):
        self.limit, self.window_s, self.clock, self.max_keys = limit, window_s, clock, max_keys
        self._hits: dict[str, deque[float]] = {}

    def _live(self, key: str) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        cutoff = self.clock() - self.window_s
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> float | None:
        """Seconds until the key may try again, or None if it is under the limit."""
        hits = self._live(key)
        return hits[0] + self.window_s - self.clock() if len(hits) >= self.limit else None

    def record(self, key: str) -> None:
        self._live(key).append(self.clock())
        if len(self._hits) > self.max_keys:
            for k in [k for k in self._hits if not self._live(k)]:
                del self._hits[k]


auth_failures = RateLimiter(limit=10, window_s=60)
requests = RateLimiter(limit=300, window_s=60)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_many(wait: float) -> HTTPException:
    return HTTPException(429, "too many requests", headers={"Retry-After": str(math.ceil(wait))})


def limit_requests(request: Request) -> None:
    ip = _ip(request)
    if (wait := requests.retry_after(ip)) is not None:
        raise _too_many(wait)
    requests.record(ip)


def require_auth(request: Request) -> None:
    """Bearer token, compared in constant time. Repeated failures lock the client out for a minute."""
    if not settings.api_token:  # only reachable in development; validate_settings forbids this elsewhere
        return
    ip = _ip(request)
    if (wait := auth_failures.retry_after(ip)) is not None:
        raise _too_many(wait)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if not (scheme.lower() == "bearer" and token and hmac.compare_digest(token.encode(), settings.api_token.encode())):
        auth_failures.record(ip)
        raise HTTPException(401, "invalid or missing token", headers={"WWW-Authenticate": "Bearer"})


PROTECTED = [Depends(limit_requests), Depends(require_auth)]


def validate_settings(s: Settings) -> None:
    """Refuses to start outside development with a missing or weak token or a wildcard CORS policy."""
    if s.app_env == "development":
        return
    if len(s.api_token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(f"API_TOKEN must be at least {MIN_TOKEN_LENGTH} characters when APP_ENV is not 'development'")
    origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
    if not origins or "*" in origins:
        raise RuntimeError("CORS_ORIGINS must list explicit origins when APP_ENV is not 'development'")
