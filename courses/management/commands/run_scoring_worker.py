"""Always-on scoring worker loop (dedicated container/service).

Runs process_scoring_queue every --interval seconds and touches a heartbeat
file the container healthcheck watches. Crash-safe: the per-job claim uses
row locking + stale reclaim, and scoring is idempotent, so killing and
restarting this loop never double-scores.
"""

import time
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand

HEARTBEAT_PATH = Path("/tmp/scoring-worker-heartbeat")


class Command(BaseCommand):
    help = "Run the scoring queue worker loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5)
        parser.add_argument("--heartbeat", type=str, default=str(HEARTBEAT_PATH))

    def handle(self, *args, **options):
        interval = options["interval"]
        heartbeat = Path(options["heartbeat"])
        self.stdout.write(f"Scoring worker loop started (interval={interval}s)")
        while True:
            call_command("process_scoring_queue", stdout=self.stdout)
            heartbeat.touch()
            time.sleep(interval)
