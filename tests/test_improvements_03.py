import httpx
import pytest
from app import core
from app.core import BenchmarkRequest, Case, analyze, latency_summary, token_f1
from fastapi.testclient import TestClient
from app.main import app


def test_multiset_f1_repetitions_empty_tokens_and_normalization():
    assert token_f1("cat cat", "cat") == pytest.approx(2 / 3)
    assert token_f1("cat dog", "cat bird") == 0.5
    assert token_f1("CAT!", "cat") == 1
    assert token_f1("", "cat") == 0
    assert token_f1("???", "!") == 1
    assert token_f1("???", "cat") == 0


def test_known_latency_distribution_and_no_measurements():
    summary = latency_summary([4, 1, 3, 2])
    assert summary == {
        "mean_latency_ms": 2.5,
        "median_latency_ms": 2.5,
        "min_latency_ms": 1,
        "max_latency_ms": 4,
        "p95_latency_ms": 4,
    }
    assert all(value is None for value in latency_summary([]).values())


def test_partial_and_failed_cases_expose_both_denominators(monkeypatch):
    calls = iter(
        [
            "cat cat",
            httpx.ReadTimeout("synthetic timeout"),
            httpx.ReadTimeout("synthetic timeout"),
            httpx.ReadTimeout("synthetic timeout"),
        ]
    )

    def local(case, request):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(core, "local_completion", local)
    request = BenchmarkRequest(
        cases=[
            Case(question="q", context="c", expected_answer="cat"),
            Case(question="q2", context="c2", expected_answer="dog"),
        ],
        adapter="local_llm",
        repeats=2,
    )
    result = analyze(request)["results"][0]
    assert result["token_f1"] == pytest.approx(2 / 3)
    assert result["completion_ratio"] == 0.25
    assert result["all_attempt_token_f1"] == pytest.approx(1 / 6)
    assert result["all_attempt_exact_match_accuracy"] == 0
    assert result["successful_runs"] == 1 and result["failed_runs"] == 3
    first, second = result["case_results"]
    assert first["successful_runs"] == 1 and first["failed_runs"] == 1
    assert first["all_attempt_token_f1"] == pytest.approx(1 / 3)
    assert second["token_f1"] is None and second["median_latency_ms"] is None
    assert second["all_attempt_token_f1"] == 0 and second["completion_ratio"] == 0
    assert "synthetic timeout" not in str(result["errors"])


def test_baseline_http_quality_and_latency_fields_are_real():
    payload = {
        "cases": [
            {"question": "color?", "context": "Blue boat.", "expected_answer": "Blue"}
        ],
        "repeats": 2,
    }
    response = TestClient(app).post("/analyze", json=payload)
    assert response.status_code == 200
    for result in response.json()["results"]:
        assert result["token_f1"] == pytest.approx(2 / 3)
        assert result["exact_match_accuracy"] == 0
        assert result["completion_ratio"] == 1
        assert (
            result["min_latency_ms"]
            <= result["median_latency_ms"]
            <= result["max_latency_ms"]
        )
        assert result["case_results"][0]["successful_runs"] == 2
