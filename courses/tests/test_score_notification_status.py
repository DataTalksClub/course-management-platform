from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone

from courses.models import Course, Homework, Project
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.score_notification_status import (
    get_homework_score_notification_status,
    get_project_score_notification_status,
    get_score_notification_status,
)


class ScoreNotificationStatusTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug="test-ml",
            title="Machine Learning",
            description="Test Course",
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw02",
            title="Homework 2",
            due_date=timezone.now() - timedelta(days=1),
        )
        self.project = Project.objects.create(
            course=self.course,
            slug="midterm",
            title="Midterm Project",
            submission_due_date=timezone.now() - timedelta(days=2),
            peer_review_due_date=timezone.now() - timedelta(days=1),
        )

    def test_not_queued_when_no_records_exist(self):
        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "not_queued")
        self.assertEqual(status.message, "")
        self.assertFalse(status.is_failed_or_retrying)
        self.assertFalse(status.is_succeeded)
        self.assertFalse(status.is_pending)

    def test_succeeded_from_audit(self):
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key="homework-score:test-ml:hw02",
            status=DatamailerSendAuditStatus.SUCCEEDED,
            enqueued_count=666,
            occurred_at=timezone.now(),
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "succeeded")
        self.assertTrue(status.is_succeeded)
        self.assertEqual(status.enqueued_count, 666)
        self.assertIn("666 emails accepted for delivery", status.message)

    def test_succeeded_from_outbox_acked(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-acked",
            event_type="homework.score_notification",
            idempotency_key="homework-score:test-ml:hw02",
            ordering_key="key-1",
            status=DatamailerOutboxStatus.ACKED,
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "succeeded")
        self.assertTrue(status.is_succeeded)

    def test_pending_status(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-pending",
            event_type="homework.score_notification",
            idempotency_key="homework-score:test-ml:hw02",
            ordering_key="key-2",
            status=DatamailerOutboxStatus.PENDING,
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "pending")
        self.assertTrue(status.is_pending)
        self.assertFalse(status.is_failed_or_retrying)

    def test_retrying_from_outbox_event(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-retry",
            event_type="homework.score_notification",
            idempotency_key="homework-score:test-ml:hw02",
            ordering_key="key-3",
            status=DatamailerOutboxStatus.RETRYING,
            attempt_count=3,
            last_error="500 Server Error: Internal Server Error",
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "retrying")
        self.assertTrue(status.is_failed_or_retrying)
        self.assertEqual(status.attempt_count, 3)
        self.assertIn("500 Server Error", status.error)
        self.assertIn("retrying automatically", status.message)

    def test_retrying_from_bulk_upsert_failure(self):
        # The main event may still be retrying or pending, but bulk upsert failed
        main_key = "homework-score:test-ml:hw02"
        bulk_key = f"recipient-list.members-bulk-upsert:{main_key}:members"
        DatamailerOutboxEvent.objects.create(
            event_id="evt-bulk-fail",
            event_type="recipient-list.members-bulk-upsert",
            idempotency_key=bulk_key,
            ordering_key="key-bulk",
            status=DatamailerOutboxStatus.RETRYING,
            attempt_count=1,
            last_error="Relay returned 500 on member upsert",
        )
        DatamailerOutboxEvent.objects.create(
            event_id="evt-main",
            event_type="homework.score_notification",
            idempotency_key=main_key,
            ordering_key="key-main",
            status=DatamailerOutboxStatus.PENDING,
        )

        status = get_score_notification_status(main_key)
        self.assertEqual(status.state, "retrying")
        self.assertTrue(status.is_failed_or_retrying)
        self.assertIn("Relay returned 500 on member upsert", status.error)

    def test_failed_from_outbox_event(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-dead",
            event_type="homework.score_notification",
            idempotency_key="homework-score:test-ml:hw02",
            ordering_key="key-4",
            status=DatamailerOutboxStatus.DEAD,
            attempt_count=24,
            last_error="Max retries reached",
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertEqual(status.state, "dead")
        self.assertTrue(status.is_failed_or_retrying)
        self.assertIn("Delivery failed", status.message)
        self.assertIn("Max retries reached", status.error)

    def test_failed_from_audit(self):
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key="homework-score:test-ml:hw02",
            status=DatamailerSendAuditStatus.FAILED,
            error="Datamailer metadata sync was not acknowledged",
            occurred_at=timezone.now(),
        )

        status = get_score_notification_status("homework-score:test-ml:hw02")
        self.assertTrue(status.is_failed_or_retrying)
        self.assertIn("Datamailer metadata sync was not acknowledged", status.error)

    def test_new_pending_attempt_supersedes_old_sync_failure(self):
        key = "homework-score:test-ml:hw02"
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=key,
            status=DatamailerSendAuditStatus.FAILED,
            error="Datamailer metadata sync was not acknowledged",
            occurred_at=timezone.now() - timedelta(days=8),
        )
        DatamailerOutboxEvent.objects.create(
            event_id="old-sync", event_type="recipient_list.members_bulk_upsert",
            idempotency_key=f"recipient-list.members-bulk-upsert:{key}:members",
            ordering_key="hw02", status=DatamailerOutboxStatus.FAILED,
            last_error="403 Client Error",
        )
        DatamailerOutboxEvent.objects.create(
            event_id="new-attempt", event_type="homework.score_notification",
            idempotency_key=key, ordering_key="hw02",
        )
        status = get_score_notification_status(key)
        self.assertEqual(status.state, "pending")
        self.assertFalse(status.is_failed_or_retrying)
        self.assertNotIn("403", status.message)

    def test_current_failure_uses_audit_update_time_after_resend(self):
        key = "homework-score:test-ml:hw02"
        audit = DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=key, status=DatamailerSendAuditStatus.FAILED,
            error="old failure", occurred_at=timezone.now() - timedelta(days=8),
        )
        DatamailerOutboxEvent.objects.create(
            event_id="current-processing", event_type="homework.score_notification",
            idempotency_key=key, ordering_key="hw02",
            status=DatamailerOutboxStatus.PROCESSING,
        )
        audit.error = "current sync failure"
        audit.save()
        status = get_score_notification_status(key)
        self.assertTrue(status.is_failed_or_retrying)
        self.assertIn("current sync failure", status.message)

    def test_failed_audit_without_live_retry_does_not_claim_automatic_retry(self):
        key = "homework-score:test-ml:hw02"
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=key,
            status=DatamailerSendAuditStatus.FAILED,
            error="Datamailer metadata sync was not acknowledged",
        )
        status = get_score_notification_status(key)
        self.assertEqual(status.state, "failed")
        self.assertNotIn("retrying automatically", status.message)

    def test_homework_and_project_wrappers(self):
        hw_status = get_homework_score_notification_status(self.homework)
        self.assertEqual(hw_status.state, "not_queued")

        proj_status = get_project_score_notification_status(self.project)
        self.assertEqual(proj_status.state, "not_queued")

    @override_settings(RELAY_URL="https://relay.example.com", RELAY_CLIENT="dtc-courses")
    def test_pending_links_to_exact_send_before_campaign_is_created(self):
        from urllib.parse import parse_qs, urlsplit
        DatamailerOutboxEvent.objects.create(
            event_id="pending-link", event_type="homework.score_notification",
            idempotency_key="homework-score:test-ml:hw02", ordering_key="test",
        )
        status = get_homework_score_notification_status(self.homework)
        query = parse_qs(urlsplit(status.campaign_url).query)
        self.assertEqual(query, {"client": ["dtc-courses"], "idempotency_key": ["homework-score:test-ml:hw02"]})

    @override_settings(RELAY_URL="https://relay.example.com", RELAY_CLIENT="dtc-courses")
    def test_legacy_acknowledged_send_uses_exact_lookup(self):
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key="homework-score:test-ml:hw02",
            status=DatamailerSendAuditStatus.SUCCEEDED,
        )
        self.assertIn("/transactional-campaigns/lookup/?", get_homework_score_notification_status(self.homework).campaign_url)
