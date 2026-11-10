import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase


class SettingsSecurityTests(TestCase):
    def load_settings(self, overrides, unset=()):
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        for key in unset:
            env.pop(key, None)
        env.update(overrides)
        env["DJANGO_SETTINGS_MODULE"] = "course_management.settings"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; from django.conf import settings; "
                    "print(json.dumps({"
                    "'debug': settings.DEBUG, "
                    "'allowed_hosts': settings.ALLOWED_HOSTS, "
                    "'csrf_origins': settings.CSRF_TRUSTED_ORIGINS, "
                    "'session_secure': settings.SESSION_COOKIE_SECURE, "
                    "'csrf_secure': settings.CSRF_COOKIE_SECURE, "
                    "'hsts': settings.SECURE_HSTS_SECONDS, "
                    "'proxy_header': settings.SECURE_PROXY_SSL_HEADER, "
                    "'ssl_redirect': settings.SECURE_SSL_REDIRECT, "
                    "'silenced_checks': settings.SILENCED_SYSTEM_CHECKS"
                    "}))"
                ),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        return result

    def test_production_refuses_missing_secret_key(self):
        result = self.load_settings(
            {"IS_LOCAL": "0"},
            unset=("SECRET_KEY",),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY", result.stderr)

    def test_production_defaults_fail_closed_and_filter_hosts(self):
        result = self.load_settings(
            {
                "IS_LOCAL": "0",
                "SECRET_KEY": "settings-test-only",
                "EXTRA_ALLOWED_HOSTS": "courses.example.com, , dev.example.com ",
            },
            unset=("DEBUG",),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout.splitlines()[-1])
        self.assertFalse(settings["debug"])
        self.assertNotIn("", settings["allowed_hosts"])
        self.assertTrue(
            all(origin.startswith("https://") for origin in settings["csrf_origins"])
        )
        self.assertTrue(settings["session_secure"])
        self.assertTrue(settings["csrf_secure"])
        self.assertGreater(settings["hsts"], 0)
        self.assertEqual(
            settings["proxy_header"], ["HTTP_X_FORWARDED_PROTO", "https"]
        )
        self.assertFalse(settings["ssl_redirect"])
        self.assertEqual(
            settings["silenced_checks"],
            ["security.W005", "security.W008", "security.W021"],
        )
