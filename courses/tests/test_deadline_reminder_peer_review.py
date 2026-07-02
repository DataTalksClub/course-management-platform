from unittest.mock import patch

from django.test import override_settings

from courses.tests.deadline_reminder_base import (
    DATAMAILER_SETTINGS,
    DeadlineReminderTestBase,
)
from courses.tests.deadline_reminder_peer_review import (
    assert_peer_review_reminder_payload,
    create_peer_review_reminder_fixture,
)


class PeerReviewDeadlineReminderCommandTest(DeadlineReminderTestBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_transient_list"
    )
    def test_peer_review_deadline_reminder_targets_unfinished_reviewers(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        fixture = create_peer_review_reminder_fixture(self, now)

        self.run_deadline_reminders(now)

        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
        assert_peer_review_reminder_payload(
            self,
            payload,
            fixture,
        )
