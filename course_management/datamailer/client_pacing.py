"""Leave headroom below Relay's 300 requests / five minutes per-IP limit.

All CMP containers on Contabo (prod web, public web, dev, workers, ad-hoc
commands) share one NATed IPv4 address. Keep CMP's budget well under 300/5min
so combined traffic never trips CloudFront WAF's per-ip-rate-limit rule.
"""
import threading
import time
from collections import deque
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .client_types import DatamailerRequest, DatamailerRequestData

EDGE_WINDOW_SECONDS = 300.0
EDGE_WINDOW_BUDGET = 180
DEFAULT_PACING_BURST = 20
DEFAULT_PACING_KEY = "relay_egress"


def pacing_budget() -> int:
    return int(getattr(settings, "RELAY_RATE_LIMIT_BUDGET", EDGE_WINDOW_BUDGET))


def pacing_window_seconds() -> float:
    return float(
        getattr(settings, "RELAY_RATE_LIMIT_WINDOW_SECONDS", EDGE_WINDOW_SECONDS)
    )


def pacing_burst() -> int:
    return int(getattr(settings, "RELAY_RATE_LIMIT_BURST", DEFAULT_PACING_BURST))


class PacedMemberRequest:
    def __init__(
        self,
        request: DatamailerRequest,
        *,
        budget: int | None = None,
        window: float | None = None,
    ):
        self.request = request
        self.budget = budget if budget is not None else pacing_budget()
        self.window = window if window is not None else pacing_window_seconds()
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


class DatabaseRelayPacer:
    """Cross-process GCRA pacer backed by PostgreSQL RelayPacingState.

    Allows small bursts (up to ``burst`` requests) without delay, then paces
    sustained traffic at ``budget / window`` across all workers/commands sharing
    the database.
    """

    def __init__(
        self,
        *,
        key: str = DEFAULT_PACING_KEY,
        budget: int | None = None,
        window: float | None = None,
        burst: int | None = None,
    ):
        self.key = key
        self.budget = budget if budget is not None else pacing_budget()
        self.window = window if window is not None else pacing_window_seconds()
        self.burst = burst if burst is not None else pacing_burst()

    def reserve_slot(self) -> float:
        if self.budget <= 0 or self.window <= 0:
            return 0.0
        from data.models import RelayPacingState

        emission = self.window / self.budget
        burst_offset = max(self.burst - 1, 0) * emission

        with transaction.atomic():
            now = timezone.now()
            state, _ = RelayPacingState.objects.select_for_update().get_or_create(
                key=self.key,
                defaults={"next_available_at": now},
            )
            tat = max(state.next_available_at, now)
            allow_at = tat - timedelta(seconds=burst_offset)
            wait_seconds = max(0.0, (allow_at - now).total_seconds())
            if wait_seconds < 0.001:
                wait_seconds = 0.0
            state.next_available_at = tat + timedelta(seconds=emission)
            state.save(update_fields=["next_available_at"])

        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return wait_seconds

    def wrap(self, request: DatamailerRequest) -> DatamailerRequest:
        def paced(data: DatamailerRequestData):
            self.reserve_slot()
            return request(data)

        return paced
