"""Optional bearer access and per-process compute admission for a single worker."""

import asyncio
import hmac
import json
import os


class AccessControl:
    def __init__(self, app):
        self.app = app
        key = os.environ.get("VENTURELAB_API_KEY", "")
        if key and (
            not 32 <= len(key) <= 256 or any(not 33 <= ord(c) <= 126 for c in key)
        ):
            raise ValueError(
                "VENTURELAB_API_KEY must contain 32–256 printable ASCII characters without spaces"
            )
        self.key = key.encode("ascii")
        try:
            limit = int(os.environ.get("VENTURELAB_MAX_INFLIGHT", "1"))
        except ValueError as exc:
            raise ValueError(
                "VENTURELAB_MAX_INFLIGHT must be an integer from 1 to 4"
            ) from exc
        if not 1 <= limit <= 4:
            raise ValueError("VENTURELAB_MAX_INFLIGHT must be an integer from 1 to 4")
        self.capacity = asyncio.Semaphore(limit)

    @staticmethod
    def public(scope):
        path = scope.get("path", "")
        return scope.get("method") in {"GET", "HEAD"} and (
            path
            in {
                "/",
                "/health",
                "/guide",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/docs/oauth2-redirect",
                "/favicon.ico",
            }
            or path.startswith(("/assets/", "/static/"))
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        public = self.public(scope)

        async def send_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                security = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"x-frame-options": b"DENY",
                    b"x-access-mode": b"token" if self.key else b"local",
                    b"cache-control": b"no-cache" if public else b"no-store",
                }
                headers = [(k, v) for k, v in headers if k.lower() not in security]
                message = {**message, "headers": headers + list(security.items())}
            await send(message)

        async def reject(status, detail, code, headers=()):
            body = json.dumps({"detail": detail, "code": code}).encode()
            await send_headers(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        *headers,
                    ],
                }
            )
            await send_headers({"type": "http.response.body", "body": body})

        if self.key and not public:
            values = [
                v for k, v in scope.get("headers", []) if k.lower() == b"authorization"
            ]
            supplied = b""
            if len(values) == 1 and len(values[0]) <= 1024:
                scheme, _, token = values[0].partition(b" ")
                if scheme.lower() == b"bearer":
                    supplied = token
            if not hmac.compare_digest(supplied, self.key):
                return await reject(
                    401,
                    "A valid server access key is required.",
                    "access_required",
                    [(b"www-authenticate", b"Bearer")],
                )
        admitted = scope.get("method") in {"POST", "PUT", "PATCH"}
        if admitted:
            if self.capacity.locked():
                return await reject(
                    429,
                    "Server is busy. Retry shortly.",
                    "capacity_exceeded",
                    [(b"retry-after", b"1")],
                )
            await self.capacity.acquire()
        try:
            return await self.app(scope, receive, send_headers)
        finally:
            if admitted:
                self.capacity.release()
