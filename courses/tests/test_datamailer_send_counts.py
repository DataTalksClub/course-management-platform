from data.models import DatamailerSendAuditType
from course_management.datamailer.payloads.send import (
    datamailer_send_counts,
)
from courses.tests.datamailer_contact_base import DatamailerContactBase


class DatamailerSendCountsTest(DatamailerContactBase):
    def test_datamailer_send_counts_marks_transactional_replay(self):
        payload = {}
        result = {
            "idempotent_replay": True,
            "enqueued": False,
            "message": {"status": "skipped"},
        }

        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSACTIONAL,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["created_count"], 0)
        self.assertEqual(counts["enqueued_count"], 0)
        self.assertEqual(counts["skipped_count"], 1)
        self.assertEqual(counts["idempotent_replay_count"], 1)

    def test_datamailer_send_counts_uses_recipient_list_response(self):
        payload = {}
        recipient_list = {"active_member_count": 3}
        result = {
            "recipient_list": recipient_list,
            "created_count": 2,
            "enqueued_count": 1,
            "skipped_count": 1,
        }

        counts = datamailer_send_counts(
            DatamailerSendAuditType.RECIPIENT_LIST,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 3)
        self.assertEqual(counts["created_count"], 2)
        self.assertEqual(counts["enqueued_count"], 1)
        self.assertEqual(counts["skipped_count"], 1)

    def test_datamailer_send_counts_falls_back_to_transient_members(self):
        active_member = {"email": "active@example.com"}
        removed_member = {"email": "removed@example.com", "status": "removed"}
        members = []
        members.append(active_member)
        members.append(removed_member)
        payload = {"members": members}
        result = {"transient_recipient_list": {}, "enqueued_count": 1}

        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["enqueued_count"], 1)
