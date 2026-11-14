"""The Hetzner release poller must survive a shared GitHub API rate limit.

2026-11-14: the account's REST quota was exhausted by other clients. Every
five-minute poll raised HTTPError 403 and paged an infra alert until the hourly
reset, although nothing was wrong with CMP. A rate limit is transient and must
skip the check without touching Coolify; any other GitHub error still fails.
"""

import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/coolify/hetzner-rollout.sh"


class _FakeGitHub(BaseHTTPRequestHandler):
    status = 403
    headers_to_send = {}
    requests = []

    def do_GET(self):
        type(self).requests.append(self.path)
        self.send_response(self.status)
        for key, value in self.headers_to_send.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"message": "private diagnostic body"}')

    def log_message(self, *args):
        pass


class HetznerRolloutRateLimitTest(SimpleTestCase):
    def run_poller(self, status, headers):
        _FakeGitHub.status = status
        _FakeGitHub.headers_to_send = headers
        _FakeGitHub.requests = []
        server = HTTPServer(("127.0.0.1", 0), _FakeGitHub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pat").write_text("ghcr-secret-value\n")
                (root / "coolify").write_text("coolify-secret-value\n")
                env = {
                    "PATH": os.environ["PATH"],
                    "HOME": directory,
                    "GHCR_PAT_FILE": str(root / "pat"),
                    "COOLIFY_TOKEN_FILE": str(root / "coolify"),
                    # Unresolvable: the test can never reach a real Coolify.
                    "COOLIFY_URL": "https://coolify.invalid",
                    "STATE_DIR": str(root / "state"),
                    "GITHUB_API_URL": f"http://127.0.0.1:{server.server_port}",
                }
                result = subprocess.run(
                    ["bash", str(SCRIPT)], env=env, capture_output=True,
                    text=True, timeout=60,
                )
                last_rollout = (root / "state" / "last_rollout").exists()
        finally:
            server.shutdown()
            server.server_close()
        output = result.stdout + result.stderr
        self.assertNotIn("ghcr-secret-value", output)
        self.assertNotIn("coolify-secret-value", output)
        self.assertFalse(last_rollout)
        self.assertEqual(len(_FakeGitHub.requests), 1)
        self.assertIn(
            "/orgs/DataTalksClub/packages/container/course-management-platform/versions",
            _FakeGitHub.requests[0],
        )
        return result

    def test_primary_rate_limit_skips_without_failing(self):
        result = self.run_poller(
            403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1794650983"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "GitHub API rate limited (HTTP 403; reset 10:09:43Z); "
            "skipping this check, no changes made",
            result.stdout,
        )
        self.assertNotIn("coolify running image", result.stdout)

    def test_secondary_rate_limit_skips_without_failing(self):
        result = self.run_poller(429, {"retry-after": "60"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GitHub API rate limited (HTTP 429; reset unknown)", result.stdout)

    def test_forbidden_without_rate_limit_still_fails(self):
        # A revoked or under-scoped PAT is not transient; it must alert.
        result = self.run_poller(403, {"x-ratelimit-remaining": "4999"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP Error 403", result.stdout + result.stderr)
        self.assertNotIn("rate limited", result.stdout)
