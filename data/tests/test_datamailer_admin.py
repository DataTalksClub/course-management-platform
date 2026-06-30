from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import Mock

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus


@dataclass(frozen=True)
class RequeueEventsFixture:
    failed: DatamailerOutboxEvent
    dead: DatamailerOutboxEvent
    acked: DatamailerOutboxEvent
    original_acked_next_attempt_at: datetime


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

    def create_requeue_events_fixture(self):
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
        return RequeueEventsFixture(
            failed=failed,
            dead=dead,
            acked=acked,
            original_acked_next_attempt_at=original_acked_next_attempt_at,
        )

    def run_requeue_selected_events_action(self):
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

        return message_user

    def assert_event_was_requeued(self, event, next_attempt_before_requeue):
        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.last_error, "")
        self.assertLess(event.next_attempt_at, next_attempt_before_requeue)

    def assert_acked_event_was_unchanged(self, fixture):
        fixture.acked.refresh_from_db()
        self.assertEqual(fixture.acked.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            fixture.acked.next_attempt_at,
            fixture.original_acked_next_attempt_at,
        )

    def assert_requeue_message(self, message_user):
        message_user.assert_called_once()
        message = message_user.call_args.args[1]
        self.assertEqual(message, "Requeued 2 Datamailer outbox event(s).")

    def test_requeue_selected_events_only_requeues_failed_and_dead_events(
        self,
    ):
        fixture = self.create_requeue_events_fixture()

        message_user = self.run_requeue_selected_events_action()

        self.assert_event_was_requeued(
            fixture.failed,
            fixture.original_acked_next_attempt_at,
        )
        self.assert_event_was_requeued(
            fixture.dead,
            fixture.original_acked_next_attempt_at,
        )
        self.assert_acked_event_was_unchanged(fixture)
        self.assert_requeue_message(message_user)
