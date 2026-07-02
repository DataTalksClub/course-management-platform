from unittest.mock import patch

from django.test import override_settings

from .datamailer_status_base import (
    DATAMAILER_SETTINGS,
    DatamailerEmailHistoryCommandTestBase,
    DatamailerMessageStatusCommandTestBase,
    DatamailerStatusCommandRunnerTestBase,
)


class DatamailerStatusCommandTest(
    DatamailerStatusCommandRunnerTestBase,
    DatamailerEmailHistoryCommandTestBase,
    DatamailerMessageStatusCommandTestBase,
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.management.commands.datamailer_status.get_email_status")
    def test_datamailer_status_command_prints_email_history(
        self,
        get_status,
    ):
        get_status.return_value = self.email_status_response()

        output = self.run_datamailer_status_command("student@example.com")

        self.assert_email_history_output(output)
        get_status.assert_called_once_with("student@example.com", limit=10)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "courses.management.commands.datamailer_status."
        "get_transactional_message_status"
    )
    def test_datamailer_status_command_prints_message_events(
        self,
        get_message_status,
    ):
        get_message_status.return_value = self.message_status_response()

        output = self.run_datamailer_status_command("--message-id", "42")

        self.assert_message_events_output(output)
        get_message_status.assert_called_once_with(42)
