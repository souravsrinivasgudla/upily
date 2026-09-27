"""Shared request dependencies: per-IP rate limiting and admin-token auth."""
import hmac
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from config import settings


def client_ip(request: Request) -> str:
    # Render's proxy appends the address it actually saw to X-Forwarded-For, so the
    # right-most entry is trustworthy. Earlier entries are whatever the client sent.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """
    In-memory sliding-window limiter, used as a FastAPI dependency.
    Good enough for a single-instance deployment; use Redis if you scale out.
    """

    def __init__(self, max_calls: int, per_seconds: int, scope: str):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self.scope = scope
        self._hits: dict[str, deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def __call__(self, request: Request) -> None:
        now = time.monotonic()
        window_start = now - self.per_seconds
        hits = self._hits[client_ip(request)]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= self.max_calls:
            retry = int(hits[0] + self.per_seconds - now) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests — try again in {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)

        if now - self._last_sweep > 300:   # drop idle clients so memory stays bounded
            self._last_sweep = now
            for key in [k for k, v in self._hits.items() if not v or v[-1] < window_start]:
                del self._hits[key]


chat_limit     = RateLimiter(max_calls=12, per_seconds=60,  scope="chat")
analyze_limit  = RateLimiter(max_calls=10, per_seconds=60,  scope="analyze")
refresh_limit  = RateLimiter(max_calls=3,  per_seconds=300, scope="refresh")
trending_limit = RateLimiter(max_calls=30, per_seconds=60,  scope="trending")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=404, detail="Not found")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin token")
