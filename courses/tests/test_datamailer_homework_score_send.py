from unittest.mock import patch

import requests
from django.test import override_settings

from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)
from course_management.datamailer.sync.score_notifications import (
    send_homework_score_notification,
)
from courses.tests.datamailer_homework_score_base import (
    DATAMAILER_SETTINGS,
    DatamailerHomeworkScoreTestBase,
    HomeworkScoreListSendExpectation,
)


class DatamailerHomeworkScoreSendSuccessTest(
    DatamailerHomeworkScoreTestBase
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_send_homework_score_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {
            "recipient_list": {
                "key": "ml-zoomcamp-2026:@e:@homework:homework-1",
                "active_member_count": 1,
            },
            "template_key": "homework-score-notification",
            "idempotency_key": "homework-score:ml-zoomcamp-2026:homework-1",
            "created_count": 1,
            "enqueued_count": 1,
            "skipped_count": 0,
            "idempotent_replay_count": 0,
        }
        homework = self.create_homework()

        result = send_homework_score_notification(homework)

        expectation = HomeworkScoreListSendExpectation(
            result=result,
            bulk_upsert=bulk_upsert,
            send_list=send_list,
            homework=homework,
        )
        self.assert_homework_score_list_send(expectation)


class DatamailerHomeworkScoreSendFailureTest(
    DatamailerHomeworkScoreTestBase
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_score_notification_does_not_send_without_metadata_ack(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.side_effect = requests.RequestException("network error")
        homework = self.create_homework()

        result = send_homework_score_notification(homework)

        self.assertIsNone(result)
        send_list.assert_not_called()
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertIn("metadata sync", audit.error)
