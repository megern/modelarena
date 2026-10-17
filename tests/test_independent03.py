import httpx
import pytest
from fastapi.testclient import TestClient
from app import core
from app.main import app


def payload():
    return {
        "cases": [{"question": "q", "context": "cat", "expected_answer": "cat"}],
        "adapter": "local_llm",
        "repeats": 3,
    }


def test_independent_latency_and_failure_denominators(monkeypatch):
    values = iter(["cat", httpx.ReadTimeout("synthetic private diagnostic"), "cat cat"])

    def completion(case, request):
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    clock = iter([0, 1_000_000, 1_000_000_000, 2_000_000_000, 2_004_000_000])
    monkeypatch.setattr(core, "local_completion", completion)
    monkeypatch.setattr(core.time, "perf_counter_ns", lambda: next(clock))
    response = TestClient(app).post("/analyze", json=payload())
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["median_latency_ms"] == 2.5
    assert result["min_latency_ms"] == 1 and result["max_latency_ms"] == 4
    assert result["completion_ratio"] == pytest.approx(2 / 3)
    assert result["token_f1"] == pytest.approx(5 / 6)
    assert result["all_attempt_token_f1"] == pytest.approx(5 / 9)
    assert result["exact_match_accuracy"] == 0.5
    assert result["all_attempt_exact_match_accuracy"] == pytest.approx(1 / 3)
    assert result["predictions"] == ["cat cat"]
    assert "synthetic private diagnostic" not in response.text


def test_independent_nested_model_json_is_reported_as_failure(monkeypatch):
    real_client = httpx.Client

    def handle(request):
        return httpx.Response(200, content=b"[" * 10000 + b"0" + b"]" * 10000)

    monkeypatch.setattr(
        core.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    data = payload()
    data["repeats"] = 1
    response = TestClient(app, raise_server_exceptions=False).post(
        "/analyze", json=data
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["failed_runs"] == 1 and result["successful_runs"] == 0
    assert result["token_f1"] is None and result["completion_ratio"] == 0


def test_independent_remote_hostname_rejected_before_transport(monkeypatch):
    monkeypatch.setenv(
        "MODELARENA_LLM_URL", "http://127.0.0.1.attacker.invalid/v1/chat/completions"
    )

    def reject_transport(**kwargs):
        pytest.fail("Rejected remote URL must never create a transport")

    monkeypatch.setattr(core.httpx, "Client", reject_transport)
    result = core.analyze(core.BenchmarkRequest(**payload()))["results"][0]
    assert result["failed_runs"] == 3 and result["completion_ratio"] == 0
