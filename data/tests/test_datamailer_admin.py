from datetime import timedelta
from unittest.mock import Mock

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus


class DatamailerOutboxAdminTest(TestCase):
    def create_outbox_event(self, *, status, event_id, last_error=""):
        return DatamailerOutboxEvent.objects.create(
            event_id=event_id,
            event_type="recipient_list.member_upsert",
            idempotency_key=f"{event_id}:idempotency",
            ordering_key="user:1",
            status=status,
            payload={"list_key": "ml-zoomcamp-2026"},
            next_attempt_at=timezone.now() + timedelta(days=1),
            last_error=last_error,
        )

    def test_requeue_selected_events_only_requeues_failed_and_dead_events(
        self,
    ):
        failed = self.create_outbox_event(
            status=DatamailerOutboxStatus.FAILED,
            event_id="failed-event",
            last_error="network error",
        )
        dead = self.create_outbox_event(
            status=DatamailerOutboxStatus.DEAD,
            event_id="dead-event",
            last_error="manual stop",
        )
        acked = self.create_outbox_event(
            status=DatamailerOutboxStatus.ACKED,
            event_id="acked-event",
        )
        original_acked_next_attempt_at = acked.next_attempt_at

        model_admin = admin.site._registry[DatamailerOutboxEvent]
        original_message_user = model_admin.message_user
        model_admin.message_user = Mock()
        request = RequestFactory().post("/admin/data/datamaileroutboxevent/")

        try:
            model_admin.requeue_selected_events(
                request,
                DatamailerOutboxEvent.objects.all(),
            )
        finally:
            message_user = model_admin.message_user
            model_admin.message_user = original_message_user

        failed.refresh_from_db()
        dead.refresh_from_db()
        acked.refresh_from_db()
        self.assertEqual(failed.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(dead.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(failed.last_error, "")
        self.assertEqual(dead.last_error, "")
        self.assertLess(failed.next_attempt_at, original_acked_next_attempt_at)
        self.assertLess(dead.next_attempt_at, original_acked_next_attempt_at)
        self.assertEqual(acked.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            acked.next_attempt_at,
            original_acked_next_attempt_at,
        )
        message_user.assert_called_once()
        message = message_user.call_args.args[1]
        self.assertEqual(message, "Requeued 2 Datamailer outbox event(s).")
