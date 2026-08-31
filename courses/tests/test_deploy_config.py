import re
from pathlib import Path

from django.test import SimpleTestCase

from course_management.datamailer.client import DEFAULT_TIMEOUT_SECONDS

GUNICORN_DEFAULT_TIMEOUT_SECONDS = 30
SAFETY_MARGIN_SECONDS = 10


class DeployConfigTestCase(SimpleTestCase):
    def gunicorn_timeout_seconds(self):
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        contents = dockerfile.read_text()
        cmd_match = re.search(r"^CMD \[(.*)\]$", contents, re.MULTILINE)
        self.assertIsNotNone(cmd_match, "Dockerfile CMD not found")
        args = [
            arg.strip().strip('"') for arg in cmd_match.group(1).split(",")
        ]
        if "--timeout" in args:
            return int(args[args.index("--timeout") + 1])
        return GUNICORN_DEFAULT_TIMEOUT_SECONDS

    def test_gunicorn_worker_timeout_exceeds_datamailer_timeout(self):
        gunicorn_timeout = self.gunicorn_timeout_seconds()

        self.assertGreaterEqual(
            gunicorn_timeout,
            DEFAULT_TIMEOUT_SECONDS + SAFETY_MARGIN_SECONDS,
            "gunicorn's worker timeout must comfortably exceed the "
            "Datamailer HTTP client timeout. Otherwise, a slow or "
            "unreachable Datamailer response gets the whole worker "
            "SIGKILLed mid-request (a hard 'Internal Server Error' with "
            "no clean message) instead of being caught as an ordinary "
            "requests.RequestException.",
        )
