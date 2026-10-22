import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Once copied into a repository, exercise that repository's deployed middleware.
if (Path(__file__).resolve().parents[1] / "app/access.py").exists():
    from app.access import AccessControl
else:
    spec = importlib.util.spec_from_file_location(
        "access", Path(__file__).with_name("access.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    AccessControl = module.AccessControl


@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    monkeypatch.delenv("VENTURELAB_API_KEY", raising=False)
    monkeypatch.delenv("VENTURELAB_MAX_INFLIGHT", raising=False)


def application():
    app = FastAPI()
    app.add_middleware(AccessControl)

    @app.post("/calculate")
    def calculate():
        return {"result": 7}

    @app.get("/jobs/private")
    def result():
        return {"input": "private test data"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def test_default_local_mode_preserves_existing_api():
    response = TestClient(application()).post("/calculate")
    assert response.status_code == 200 and response.json() == {"result": 7}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-access-mode"] == "local"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_key_guards_calculations_and_private_job_results(monkeypatch):
    key = "synthetic-" + "k" * 32
    monkeypatch.setenv("VENTURELAB_API_KEY", key)
    client = TestClient(application())
    for method, path in [("post", "/calculate"), ("get", "/jobs/private")]:
        denied = getattr(client, method)(path)
        assert denied.status_code == 401 and "private test data" not in denied.text
        assert denied.headers["www-authenticate"] == "Bearer"
        assert (
            getattr(client, method)(
                path, headers={"Authorization": "bEaReR " + key}
            ).status_code
            == 200
        )
        assert (
            getattr(client, method)(
                path, headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        )
    health = client.get("/health")
    assert health.status_code == 200 and health.headers["x-access-mode"] == "token"
    assert client.get("/openapi.json").status_code == 200
    duplicate = client.post(
        "/calculate",
        headers=[
            ("Authorization", "Bearer " + key),
            ("Authorization", "Bearer " + key),
        ],
    )
    assert duplicate.status_code == 401


def test_unauthorized_body_is_not_read(monkeypatch):
    monkeypatch.setenv("VENTURELAB_API_KEY", "synthetic-" + "x" * 32)

    async def check():
        messages = []

        async def receive():
            raise AssertionError(
                "Unauthorized requests must be rejected before reading the body"
            )

        async def send(message):
            messages.append(message)

        await AccessControl(application())(
            {"type": "http", "method": "POST", "path": "/calculate", "headers": []},
            receive,
            send,
        )
        assert messages[0]["status"] == 401

    asyncio.run(check())


@pytest.mark.parametrize(
    "value", ["short", "x" * 257, "not ascii " + "ع" * 32, " " * 32]
)
def test_invalid_key_configuration_fails_closed(monkeypatch, value):
    monkeypatch.setenv("VENTURELAB_API_KEY", value)
    with pytest.raises(ValueError, match="32–256"):
        AccessControl(application())


@pytest.mark.parametrize("value", ["0", "5", "no"])
def test_invalid_capacity_fails_at_startup(monkeypatch, value):
    monkeypatch.setenv("VENTURELAB_MAX_INFLIGHT", value)
    with pytest.raises(ValueError, match="1 to 4"):
        AccessControl(application())


def test_capacity_rejects_parallel_work_and_recovers():
    async def check():
        started, release = asyncio.Event(), asyncio.Event()
        app = FastAPI()
        app.add_middleware(AccessControl)

        @app.post("/slow")
        async def slow():
            started.set()
            await release.wait()
            return {"done": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = asyncio.create_task(client.post("/slow"))
            await asyncio.wait_for(started.wait(), 2)
            second = await client.post("/slow")
            assert second.status_code == 429 and second.headers["retry-after"] == "1"
            release.set()
            assert (await first).status_code == 200
            assert (await client.post("/slow")).status_code == 200

    asyncio.run(check())
