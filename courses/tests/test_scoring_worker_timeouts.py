from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from course_management.db_timeouts import set_statement_timeout
from courses.management.commands.run_scoring_worker import (
    SCORING_STATEMENT_TIMEOUT_MS,
    Command,
)


class DatabaseStatementTimeoutTests(SimpleTestCase):
    @patch("course_management.db_timeouts.connection")
    def test_sets_session_timeout_on_postgres(self, connection):
        connection.vendor = "postgresql"
        cursor = connection.cursor.return_value.__enter__.return_value

        self.assertTrue(set_statement_timeout(120_000))

        cursor.execute.assert_called_once_with(
            "SELECT set_config('statement_timeout', %s, false)",
            ["120000ms"],
        )

    @patch("course_management.db_timeouts.connection")
    def test_skips_session_timeout_on_sqlite(self, connection):
        connection.vendor = "sqlite"

        self.assertFalse(set_statement_timeout(120_000))
        connection.cursor.assert_not_called()

    @patch("courses.management.commands.run_scoring_worker.call_command")
    @patch("courses.management.commands.run_scoring_worker.set_statement_timeout")
    def test_scoring_loop_uses_longer_timeout(self, set_timeout, call_command):
        command = Command()
        temp_root = Path(__file__).resolve().parents[2] / ".tmp"
        temp_root.mkdir(exist_ok=True)

        with TemporaryDirectory(dir=temp_root) as temp_dir:
            command.handle(
                interval=0,
                heartbeat=str(Path(temp_dir) / "heartbeat"),
                max_iterations=1,
            )

        set_timeout.assert_called_once_with(SCORING_STATEMENT_TIMEOUT_MS)
        call_command.assert_called_once_with(
            "run_cmp_job", "scoring", stdout=command.stdout
        )
