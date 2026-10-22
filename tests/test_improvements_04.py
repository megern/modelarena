import threading
import time
import pytest
from fastapi.testclient import TestClient
from app import core, main
from app.core import BenchmarkRequest, Case, analyze
from app.execution import ExecutionControl, ExecutionInterrupted
from app.jobs import JobManager, JobSubmission, QueueFull


def submission(label="q", budget=10):
    return JobSubmission(
        request=BenchmarkRequest(
            cases=[Case(question=label, context="cat.", expected_answer="cat")],
            repeats=2,
        ),
        budget_seconds=budget,
    )


def finished(manager, identifier, timeout=2):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        state = manager.snapshot(identifier)
        if state["status"] not in {"running", "queued"}:
            return state
        time.sleep(0.005)
    raise AssertionError("Job did not finish within test timeout")


def test_queue_admission_queued_cancellation_and_one_worker():
    entered, release = threading.Event(), threading.Event()
    executed = []

    def runner(request, execution):
        executed.append(request.cases[0].question)
        entered.set()
        while not release.wait(0.005):
            execution.checkpoint()
        execution.progress(1, 1, 1, 0)
        return {"ok": True}

    manager = JobManager(runner=runner)
    first = manager.submit(submission("first"))
    assert entered.wait(1)
    second = manager.submit(submission("second"))
    third = manager.submit(submission("third"))
    assert second["status"] == third["status"] == "queued"
    with pytest.raises(QueueFull):
        manager.submit(submission("fourth"))
    assert manager.cancel(second["job_id"])["status"] == "cancelled"
    release.set()
    assert finished(manager, first["job_id"])["status"] == "succeeded"
    assert finished(manager, third["job_id"])["status"] == "succeeded"
    assert executed == ["first", "third"]


def test_running_cancel_is_cooperative_not_a_fabricated_finished_state():
    entered = threading.Event()

    def runner(request, execution):
        entered.set()
        while True:
            execution.checkpoint()
            time.sleep(0.005)

    manager = JobManager(runner=runner)
    job = manager.submit(submission())
    assert entered.wait(1)
    state = manager.cancel(job["job_id"])
    assert state["cancel_requested"]
    assert state["status"] in {"running", "cancelled"}
    state = finished(manager, job["job_id"])
    assert state["status"] == "cancelled" and state["result"] is None


def test_actual_baseline_job_http_progress_and_unknown_job(monkeypatch):
    manager = JobManager()
    monkeypatch.setattr(main, "manager", manager)
    client = TestClient(main.app)
    response = client.post("/jobs", json=submission().model_dump())
    assert response.status_code == 202
    state = finished(manager, response.json()["job_id"])
    assert state["status"] == "succeeded"
    assert state["progress"] == {
        "completed": 4,
        "total": 4,
        "successful": 4,
        "failed": 0,
    }
    assert state["result"]["results"][0]["successful_runs"] == 2
    assert client.get("/jobs/unknown").status_code == 404
    assert client.delete("/jobs/unknown").status_code == 404
    assert (
        client.post(
            "/jobs",
            json={"request": submission().request.model_dump(), "budget_seconds": 301},
        ).status_code
        == 422
    )


def test_deterministic_overall_budget_checkpoint_and_output_bound(monkeypatch):
    now = [0.0]
    control = ExecutionControl(0.1, clock=lambda: now[0])

    def predict(case, method):
        now[0] += 0.06
        return "cat"

    monkeypatch.setattr(core, "predict", predict)
    with pytest.raises(ExecutionInterrupted, match="budget_exceeded"):
        analyze(submission().request, execution=control)
    control = ExecutionControl(10)
    with pytest.raises(ExecutionInterrupted, match="output_limit_exceeded"):
        control.accept_output("a" * 524289)


def test_ttl_expiry_and_sanitized_runner_failures():
    now = [0.0]
    manager = JobManager(
        runner=lambda request, execution: {"ok": True},
        ttl_seconds=1,
        clock=lambda: now[0],
    )
    job = manager.submit(submission())
    assert finished(manager, job["job_id"])["status"] == "succeeded"
    now[0] = 2
    with pytest.raises(KeyError):
        manager.snapshot(job["job_id"])

    def broken(request, execution):
        raise RuntimeError("private server response must not leak")

    manager = JobManager(runner=broken)
    job = manager.submit(submission())
    state = finished(manager, job["job_id"])
    assert (
        state["status"] == "failed" and state["error"] == "benchmark_execution_failed"
    )
    assert "private" not in str(state)
