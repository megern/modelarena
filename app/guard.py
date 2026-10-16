"""Bound HTTP JSON requests before parsing expensive application inputs."""

import json
import math
from starlette.responses import JSONResponse


class InputGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        chunks = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > 2097152:
                return await JSONResponse(
                    {"detail": "Request exceeds 2 MiB"}, status_code=413
                )(scope, receive, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        payload = b"".join(chunks)

        def validate(value, depth=0):
            if depth > 32:
                raise ValueError("JSON nesting exceeds 32 levels")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if abs(value) > 1e100 or not math.isfinite(value):
                    raise ValueError(
                        "Numeric values must be finite with magnitude at most 1e100"
                    )
            elif isinstance(value, dict):
                for item in value.values():
                    validate(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    validate(item, depth + 1)

        try:
            if payload:
                validate(json.loads(payload))
        except (ValueError, OverflowError, RecursionError) as exc:
            return await JSONResponse({"detail": str(exc)}, status_code=422)(
                scope, receive, send
            )
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
