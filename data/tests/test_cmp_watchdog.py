"""Run watchdog behavior with stubbed Docker, Relay and syslog in CI."""

import os
from pathlib import Path
import subprocess

from django.test import SimpleTestCase


class CmpWatchdogTests(SimpleTestCase):
    def test_diagnostics_hysteresis_and_recovery(self):
        root = Path(__file__).resolve().parents[2]
        scratch = root / ".tmp"
        scratch.mkdir(exist_ok=True)
        result = subprocess.run(
            ["bash", str(root / "deploy/coolify/test-cmp-watchdogs.sh")],
            cwd=root,
            env={
                **os.environ,
                "WATCHDOG_TEST_TMPDIR": str(scratch),
                "CMP_APP_PREFIX": "web-avcfd5kwb7cj9r1tx4ygjs6v",
                "CMP_FAIL_THRESHOLD": "2",
            },
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
