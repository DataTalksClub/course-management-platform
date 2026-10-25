"""Leave headroom below Relay's 300 requests / five minutes per-IP limit."""
import time

from .client_types import DatamailerRequest, DatamailerRequestData


class PacedMemberRequest:
    def __init__(self, request: DatamailerRequest):
        self.request = request
        self.next_start = 0.0

    def __call__(self, data: DatamailerRequestData):
        delay = self.next_start - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        # Pace request starts, including consecutive events on this client.
        # Network time counts toward the interval. Errors still propagate.
        self.next_start = time.monotonic() + 1.25
        return self.request(data)
