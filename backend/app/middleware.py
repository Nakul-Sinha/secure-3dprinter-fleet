"""API hardening: rate limiting and idempotency keys."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

# client key -> timestamps of recent requests
_hits: dict[str, deque] = defaultdict(deque)
# idempotency key -> stored response
_idem: dict[str, dict] = {}

WINDOW_S = 60.0
MAX_PER_WINDOW = 240
IDEM_LIMIT = 5000


def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth:
        return auth[-32:]
    return request.client.host if request.client else "anonymous"


def rate_limited(request: Request) -> bool:
    key = _client_key(request)
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_PER_WINDOW:
        return True
    q.append(now)
    return False


async def guard_middleware(request: Request, call_next):
    """Rate limit every API call and make POSTs idempotent when a key is given."""
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)

    if rate_limited(request):
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})

    idem_key = request.headers.get("idempotency-key", "")
    if request.method == "POST" and idem_key:
        cache_key = f"{_client_key(request)}|{path}|{idem_key}"
        if cache_key in _idem:
            stored = _idem[cache_key]
            return JSONResponse(status_code=stored["status"], content=stored["body"],
                                headers={"Idempotent-Replay": "true"})
        response = await call_next(request)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if response.status_code < 400 and len(_idem) < IDEM_LIMIT:
            try:
                import json

                _idem[cache_key] = {"status": response.status_code, "body": json.loads(body or b"{}")}
            except Exception:
                pass
        from starlette.responses import Response

        return Response(content=body, status_code=response.status_code,
                        headers=dict(response.headers), media_type=response.media_type)

    return await call_next(request)


def reset_guards_for_tests() -> None:
    _hits.clear()
    _idem.clear()
