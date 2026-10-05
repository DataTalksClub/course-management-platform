from unittest.mock import patch

import requests
from django.test import override_settings

from course_management.datamailer.sync.score_notifications import (
    queue_homework_score_notification,
)
from courses.tests.datamailer_homework_score_base import (
    RELAY_SETTINGS,
    DatamailerHomeworkScoreTestBase,
)
from data.models import DatamailerOutboxStatus


class DatamailerOutboxHomeworkScoreTest(DatamailerHomeworkScoreTestBase):
    def process_due_outbox(self):
        from course_management.datamailer_outbox_runs import (
            process_due_datamailer_outbox,
        )

        process_due_datamailer_outbox()

    @override_settings(**RELAY_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_enqueue_does_not_call_datamailer(self, bulk_upsert, send_list):
        homework = self.create_homework()

        event = queue_homework_score_notification(homework)

        bulk_upsert.assert_not_called()
        send_list.assert_not_called()
        self.assertEqual(event.event_type, "homework.score_notification")
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)
        self.assertEqual(event.payload, {"homework_id": homework.pk})

    @override_settings(**RELAY_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_process_outbox_sends_homework_score_notification(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {"enqueued_count": 1}
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        self.create_homework_submission(homework, user)
        event = queue_homework_score_notification(homework)

        self.process_due_outbox()

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        send_list.assert_called_once()
        bulk_upsert.assert_called()

    @override_settings(**RELAY_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists."
        "DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_process_outbox_retries_when_send_is_not_acknowledged(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.side_effect = requests.RequestException("network error")
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        self.create_homework_submission(homework, user)
        event = queue_homework_score_notification(homework)

        self.process_due_outbox()

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        send_list.assert_called_once()
