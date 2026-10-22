"""Independent review regressions for the shared ASGI access middleware."""

import asyncio
import importlib.util
from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.access import AccessControl

KEY = "synthetic-independent-" + "z" * 32


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("VENTURELAB_API_KEY", KEY)
    monkeypatch.setenv("VENTURELAB_MAX_INFLIGHT", "1")


def test_private_get_aliases_query_cookie_and_oversized_headers_never_authorize():
    async def check():
        called = []

        async def inner(scope, receive, send):
            called.append(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"private"})

        middleware = AccessControl(inner)
        for path in [
            "/jobs/private",
            "/assets-evil",
            "/staticjunk",
            "/health/private",
            "/Health",
            "/openapi.json/private",
        ]:
            for headers in [
                [],
                [(b"cookie", b"Authorization=Bearer " + KEY.encode())],
                [(b"x-api-key", KEY.encode())],
                [(b"authorization", b"Bearer " + b"x" * 1025)],
                [
                    (b"authorization", b"Bearer " + KEY.encode()),
                    (b"Authorization", b"Bearer " + KEY.encode()),
                ],
            ]:
                messages = []

                async def receive():
                    raise AssertionError("Rejected input must not be read")

                async def send(message):
                    messages.append(message)

                await middleware(
                    {
                        "type": "http",
                        "method": "GET",
                        "path": path,
                        "query_string": b"access_token=" + KEY.encode(),
                        "headers": headers,
                    },
                    receive,
                    send,
                )
                assert messages[0]["status"] == 401
                assert KEY.encode() not in messages[-1]["body"]
        assert not called

    asyncio.run(check())


def test_four_admissions_reject_fifth_keep_health_live_and_release_on_errors(
    monkeypatch,
):
    monkeypatch.setenv("VENTURELAB_MAX_INFLIGHT", "4")

    async def check():
        entered = 0
        ready = asyncio.Event()
        release = asyncio.Event()
        app = FastAPI()
        app.add_middleware(AccessControl)

        @app.post("/work")
        async def work():
            nonlocal entered
            entered += 1
            if entered == 4:
                ready.set()
            await release.wait()
            raise HTTPException(422, "Synthetic processing error")

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            jobs = [asyncio.create_task(client.post("/work")) for _ in range(4)]
            await asyncio.wait_for(ready.wait(), 2)
            refused = await client.post("/work")
            assert refused.status_code == 429
            assert (
                refused.headers["retry-after"] == "1"
                and refused.headers["cache-control"] == "no-store"
            )
            assert (await client.get("/health")).status_code == 200
            assert entered == 4
            release.set()
            for result in await asyncio.gather(*jobs):
                assert (
                    result.status_code == 422
                    and result.headers["cache-control"] == "no-store"
                )
            assert (await client.post("/work")).status_code == 422

    asyncio.run(check())


def test_cancellation_and_unhandled_exception_cannot_leak_compute_slot():
    async def check():
        entered = asyncio.Event()
        release = asyncio.Event()
        mode = "cancel"

        async def inner(scope, receive, send):
            entered.set()
            if mode == "cancel":
                await release.wait()
            elif mode == "raise":
                raise RuntimeError("Synthetic failure")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"cache-control", b"public")],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = AccessControl(inner)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/work",
            "headers": [(b"authorization", ("Bearer " + KEY).encode())],
        }
        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        pending = asyncio.create_task(middleware(scope, receive, send))
        await asyncio.wait_for(entered.wait(), 2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        mode = "raise"
        with pytest.raises(RuntimeError):
            await middleware(scope, receive, send)
        mode = "ok"
        await middleware(scope, receive, send)
        assert messages[-2]["status"] == 200
        assert dict(messages[-2]["headers"])[b"cache-control"] == b"no-store"

    asyncio.run(check())


def test_unauthorized_work_does_not_reserve_a_slot():
    async def check():
        entered = 0

        async def inner(scope, receive, send):
            nonlocal entered
            entered += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = AccessControl(inner)

        async def receive():
            return {"type": "http.request", "body": b""}

        results = []

        async def send(message):
            results.append(message)

        for _ in range(20):
            await middleware(
                {"type": "http", "path": "/work", "method": "POST", "headers": []},
                receive,
                send,
            )
        await middleware(
            {
                "type": "http",
                "path": "/work",
                "method": "POST",
                "headers": [(b"authorization", ("Bearer " + KEY).encode())],
            },
            receive,
            send,
        )
        assert entered == 1 and results[-2]["status"] == 200

    asyncio.run(check())
