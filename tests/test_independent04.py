import threading
import time
import pytest
from app import jobs
from app.core import BenchmarkRequest
from app.jobs import JobManager, JobSubmission


def submission():
    return JobSubmission(
        request=BenchmarkRequest(
            cases=[{"question": "q", "context": "a", "expected_answer": "a"}], repeats=1
        )
    )


def terminal(manager, identifier):
    until = time.monotonic() + 2
    while time.monotonic() < until:
        state = manager.snapshot(identifier)
        if state["status"] not in {"running", "queued"}:
            return state
        time.sleep(0.002)
    raise AssertionError("worker did not finish")


def test_cancel_during_result_serialization_cannot_publish_success(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = jobs.json.dumps

    def blocked(value):
        entered.set()
        assert release.wait(2)
        return original(value)

    monkeypatch.setattr(jobs.json, "dumps", blocked)
    manager = JobManager(runner=lambda request, execution: {"ok": True})
    job = manager.submit(submission())
    assert entered.wait(1)
    state = manager.cancel(job["job_id"])
    assert state["cancel_requested"] and state["status"] == "running"
    release.set()
    state = terminal(manager, job["job_id"])
    assert state["status"] == "cancelled" and state["result"] is None


def test_completed_result_retention_bound_and_request_release():
    manager = JobManager(runner=lambda request, execution: {"ok": True})
    identifiers = []
    for _ in range(12):
        job = manager.submit(submission())
        identifiers.append(job["job_id"])
        assert terminal(manager, job["job_id"])["status"] == "succeeded"
    assert len(manager.jobs) == 8
    assert all(job.request is None for job in manager.jobs.values())
    with pytest.raises(KeyError):
        manager.snapshot(identifiers[0])


def test_result_size_limit_is_enforced_and_not_success():
    manager = JobManager(runner=lambda request, execution: {"large": "x" * 1048576})
    job = manager.submit(submission())
    state = terminal(manager, job["job_id"])
    assert state["status"] == "failed" and state["error"] == "result_limit_exceeded"
    assert state["result"] is None


def test_budget_expiring_during_result_serialization_cannot_publish_success(
    monkeypatch,
):
    now = [0.0]
    original = jobs.json.dumps

    def expire(value):
        now[0] = 121.0
        return original(value)

    monkeypatch.setattr(jobs.json, "dumps", expire)
    manager = JobManager(
        runner=lambda request, execution: {"ok": True}, clock=lambda: now[0]
    )
    job = manager.submit(submission())
    state = terminal(manager, job["job_id"])
    assert state["status"] == "timed_out"
    assert state["error"] == "budget_exceeded" and state["result"] is None
