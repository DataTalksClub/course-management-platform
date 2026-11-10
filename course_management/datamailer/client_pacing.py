"""Leave headroom below Relay's 300 requests / five minutes per-IP limit.

A sliding window, not a fixed interval: bursts are free until the window
holds EDGE_WINDOW_BUDGET request starts, then each start waits for the
oldest one to age out. A ~1000-recipient fan-out is ~35 requests, so it
goes out at full speed instead of one request per 1.25 s (which capped
transient-list sends near 22 msg/s). Thread-safe: parallel chunk senders
share one budget.
"""
import threading
import time
from collections import deque

from .client_types import DatamailerRequest, DatamailerRequestData

EDGE_WINDOW_SECONDS = 300.0
EDGE_WINDOW_BUDGET = 240


class PacedMemberRequest:
    def __init__(
        self,
        request: DatamailerRequest,
        *,
        budget: int = EDGE_WINDOW_BUDGET,
        window: float = EDGE_WINDOW_SECONDS,
    ):
        self.request = request
        self.budget = budget
        self.window = window
        self.starts: deque[float] = deque()
        self.lock = threading.Lock()

    def _reserve_start(self):
        with self.lock:
            while True:
                now = time.monotonic()
                while self.starts and now - self.starts[0] >= self.window:
                    self.starts.popleft()
                if len(self.starts) < self.budget:
                    self.starts.append(now)
                    return
                # Network time counts toward the window. Errors still propagate.
                time.sleep(self.window - (now - self.starts[0]))

    def __call__(self, data: DatamailerRequestData):
        self._reserve_start()
        return self.request(data)
