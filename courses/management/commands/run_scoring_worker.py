"""Always-on scoring worker loop (dedicated container/service).

Runs `run_cmp_job scoring` every --interval seconds and touches a heartbeat
file the container healthcheck watches. Routing through run_cmp_job (instead
of calling process_scoring_queue directly) records CmpJobState('scoring')
last_started_at/last_success_at/last_failed_at under the cmp-job:scoring
singleton lock, which check_cmp_workers requires to stay fresh
(scoring:success_stale, 600s). Crash-safe: the per-job claim uses row
locking + stale reclaim, and scoring is idempotent, so killing and
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
        parser.add_argument(
            "--max-iterations",
            type=int,
            default=None,
            help="Stop after N loop iterations (tests only; default: run forever).",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        heartbeat = Path(options["heartbeat"])
        max_iterations = options.get("max_iterations")
        self.stdout.write(f"Scoring worker loop started (interval={interval}s)")
        iteration = 0
        while True:
            call_command("run_cmp_job", "scoring", stdout=self.stdout)
            heartbeat.touch()
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            time.sleep(interval)
