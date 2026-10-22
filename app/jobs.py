"""One cooperative worker, two queued requests, bounded ephemeral results."""

from collections import deque
from dataclasses import dataclass, field
import json
import threading
import time
import uuid
from pydantic import BaseModel, ConfigDict, Field
from .core import BenchmarkRequest, analyze
from .execution import ExecutionControl, ExecutionInterrupted


class JobSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: BenchmarkRequest
    budget_seconds: float = Field(default=120, ge=0.1, le=300, allow_inf_nan=False)


class QueueFull(Exception):
    pass


@dataclass
class Job:
    id: str
    request: BenchmarkRequest | None
    budget: float
    created: float
    status: str = "queued"
    finished: float | None = None
    result: dict | None = None
    error: str | None = None
    progress: dict = field(
        default_factory=lambda: {
            "completed": 0,
            "total": 0,
            "successful": 0,
            "failed": 0,
        }
    )
    cancel_event: threading.Event = field(default_factory=threading.Event)


class JobManager:
    def __init__(self, runner=analyze, ttl_seconds=300, clock=time.monotonic):
        self.runner = runner
        self.ttl = ttl_seconds
        self.clock = clock
        self.lock = threading.RLock()
        self.jobs = {}
        self.queue = deque()
        self.running = None
        self.worker = None

    def _expire(self):
        expired = [
            key
            for key, job in self.jobs.items()
            if job.finished is not None and self.clock() - job.finished >= self.ttl
        ]
        for key in expired:
            del self.jobs[key]
        completed = sorted(
            (job for job in self.jobs.values() if job.finished is not None),
            key=lambda job: job.finished,
        )
        for job in completed[:-8]:
            del self.jobs[job.id]

    def submit(self, submission):
        with self.lock:
            self._expire()
            if self.running is not None and len(self.queue) >= 2:
                raise QueueFull(
                    "One running job and two queued jobs are already admitted"
                )
            job = Job(
                uuid.uuid4().hex,
                submission.request.model_copy(deep=True),
                submission.budget_seconds,
                self.clock(),
            )
            total = (
                len(job.request.cases)
                * job.request.repeats
                * (2 if job.request.adapter == "baselines" else 1)
            )
            job.progress["total"] = total
            self.jobs[job.id] = job
            if self.running is None:
                self.running = job.id
                job.status = "running"
                self.worker = threading.Thread(
                    target=self._work,
                    args=(job,),
                    daemon=True,
                    name="modelarena-worker",
                )
                self.worker.start()
            else:
                self.queue.append(job.id)
            return self.snapshot(job.id)

    def _work(self, job):
        while job is not None:

            def progress(completed, total, successful, failed):
                with self.lock:
                    job.progress = {
                        "completed": completed,
                        "total": total,
                        "successful": successful,
                        "failed": failed,
                    }

            control = ExecutionControl(
                job.budget, job.cancel_event, progress, self.clock
            )
            try:
                result = self.runner(job.request, execution=control)
                control.checkpoint()
                if len(json.dumps(result).encode("utf-8")) > 1048576:
                    raise ExecutionInterrupted("result_limit_exceeded")
                with self.lock:
                    # Cancellation and successful publication share this lock and checkpoint.
                    control.checkpoint()
                    job.result = result
                    job.status = "succeeded"
            except ExecutionInterrupted as error:
                with self.lock:
                    job.error = error.reason
                    job.status = (
                        "cancelled"
                        if error.reason == "cancelled"
                        else "timed_out"
                        if error.reason == "budget_exceeded"
                        else "failed"
                    )
            except Exception:
                # Do not expose exception strings or model-server bodies through status endpoints.
                with self.lock:
                    job.error = "benchmark_execution_failed"
                    job.status = "failed"
            with self.lock:
                job.finished = self.clock()
                job.request = None
                self.running = None
                job = None
                while self.queue:
                    next_id = self.queue.popleft()
                    candidate = self.jobs.get(next_id)
                    if candidate and candidate.status == "queued":
                        job = candidate
                        job.status = "running"
                        self.running = job.id
                        break
                self._expire()

    def snapshot(self, identifier):
        with self.lock:
            self._expire()
            job = self.jobs.get(identifier)
            if job is None:
                raise KeyError(identifier)
            return {
                "job_id": job.id,
                "status": job.status,
                "progress": dict(job.progress),
                "cancel_requested": job.cancel_event.is_set(),
                "budget_seconds": job.budget,
                "age_seconds": max(0, self.clock() - job.created),
                "queue_position": list(self.queue).index(job.id) + 1
                if job.id in self.queue
                else None,
                "expires_in_seconds": max(0, self.ttl - (self.clock() - job.finished))
                if job.finished is not None
                else None,
                "result": job.result,
                "error": job.error,
                "ephemeral": True,
            }

    def cancel(self, identifier):
        with self.lock:
            self._expire()
            job = self.jobs.get(identifier)
            if job is None:
                raise KeyError(identifier)
            if job.status not in {"queued", "running"}:
                return self.snapshot(identifier)
            job.cancel_event.set()
            if job.status == "queued":
                self.queue.remove(identifier)
                job.status = "cancelled"
                job.error = "cancelled_before_execution"
                job.finished = self.clock()
                job.request = None
            return self.snapshot(identifier)


manager = JobManager()
