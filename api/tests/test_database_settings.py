import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase


class DatabaseSettingsTests(TestCase):
    def test_postgres_uses_bounded_connect_and_socket_timeouts(self):
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": (
                    "postgresql://cmp:test@db.example.test:5432/cmp"
                ),
                "DJANGO_SETTINGS_MODULE": "course_management.settings",
                "IS_LOCAL": "1",
                "SECRET_KEY": "settings-test-only",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; from django.conf import settings; "
                    "print(json.dumps(settings.DATABASES['default']))"
                ),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            check=True,
            text=True,
        )

        database = json.loads(result.stdout.splitlines()[-1])
        options = database["OPTIONS"]
        self.assertEqual(options["connect_timeout"], 5)
        self.assertEqual(options["keepalives"], 1)
        self.assertEqual(options["keepalives_idle"], 30)
        self.assertEqual(options["keepalives_interval"], 10)
        self.assertEqual(options["keepalives_count"], 3)
        self.assertEqual(options["tcp_user_timeout"], 20000)
