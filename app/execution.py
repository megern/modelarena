"""Cooperative execution controls; threads are never forcibly terminated."""

import threading
import time


class ExecutionInterrupted(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class ExecutionControl:
    def __init__(self, budget, cancel_event=None, progress=None, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + budget
        self.cancel_event = cancel_event or threading.Event()
        self.callback = progress
        self.output_bytes = 0

    def remaining(self):
        return max(0.0, self.deadline - self.clock())

    def checkpoint(self):
        if self.cancel_event.is_set():
            raise ExecutionInterrupted("cancelled")
        if self.remaining() <= 0:
            raise ExecutionInterrupted("budget_exceeded")

    def accept_output(self, value):
        self.output_bytes += len(value.encode("utf-8"))
        if self.output_bytes > 524288:
            raise ExecutionInterrupted("output_limit_exceeded")

    def progress(self, completed, total, successful, failed):
        if self.callback:
            self.callback(completed, total, successful, failed)
