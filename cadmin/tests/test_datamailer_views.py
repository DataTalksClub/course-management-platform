from dataclasses import dataclass

from django.test import Client, TestCase
from django.urls import reverse

from courses.models import User
from data.models import (
    DatamailerContactEvent,
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


@dataclass(frozen=True)
class ContactEventData:
    event_id: str
    event_type: str
    email: str
    audience: str = ""
    duplicate_count: int = 0


class DatamailerCadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(**credentials)
        User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def datamailer_operations_url(self):
        return reverse("cadmin_datamailer_operations")

    def datamailer_events_url(self):
        return reverse("cadmin_datamailer_events")

    def create_datamailer_operations_records(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-outbox-failed",
            event_type="recipient_list.member_upsert",
            idempotency_key="idem-outbox-failed",
            status=DatamailerOutboxStatus.FAILED,
            last_error="network error",
        )
        DatamailerOutboxDispatchRun.objects.create(
            status=DatamailerOutboxDispatchRunStatus.SUCCESS,
            processed_count=3,
            acked_count=3,
        )
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key="send-ok",
            intended_count=5,
            created_count=4,
            enqueued_count=4,
            skipped_count=1,
        )
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            status=DatamailerSendAuditStatus.FAILED,
            idempotency_key="send-failed",
            template_key="course-registration-confirmation",
            error="Datamailer failed",
        )

    def assert_datamailer_operations_content(self, response):
        self.assertContains(response, "Datamailer operations")
        self.assertContains(response, "network error")
        self.assertContains(response, "Datamailer failed")
        self.assertContains(response, self.datamailer_events_url())
        self.assertContains(response, "Bootstrap and repair")
        self.assertContains(
            response,
            "sync_datamailer_contacts --active-only",
        )
        self.assertContains(
            response,
            "sync_datamailer_recipient_lists &lt;kind&gt; --reconcile",
        )
        self.assertContains(
            response,
            "audit_datamailer_recipient_lists &lt;kind&gt; --repair",
        )
        self.assertContains(response, "project-passed")

    def assert_datamailer_send_totals(self, response):
        self.assertEqual(response.context["send_totals"]["intended_count"], 5)
        self.assertEqual(response.context["send_totals"]["created_count"], 4)
        self.assertEqual(response.context["send_totals"]["enqueued_count"], 4)
        self.assertEqual(response.context["send_totals"]["skipped_count"], 1)
        self.assertEqual(response.context["send_totals"]["failed"], 1)

    def create_datamailer_outbox_event(self, event_id, status, last_error):
        return DatamailerOutboxEvent.objects.create(
            event_id=event_id,
            event_type="recipient_list.member_upsert",
            idempotency_key=f"idem-{event_id}",
            status=status,
            last_error=last_error,
        )

    def create_requeue_outbox_events(self):
        return {
            "failed": self.create_datamailer_outbox_event(
                "evt-failed",
                DatamailerOutboxStatus.FAILED,
                "network error",
            ),
            "dead": self.create_datamailer_outbox_event(
                "evt-dead",
                DatamailerOutboxStatus.DEAD,
                "permanent error",
            ),
            "acked": self.create_datamailer_outbox_event(
                "evt-acked",
                DatamailerOutboxStatus.ACKED,
                "old error",
            ),
        }

    def post_datamailer_requeue(self):
        self.login_admin()
        return self.client.post(
            self.datamailer_operations_url(),
            {"action": "requeue"},
        )

    def assert_outbox_event_requeued(self, event):
        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.last_error, "")

    def assert_outbox_event_unchanged(self, event, status, last_error):
        event.refresh_from_db()
        self.assertEqual(event.status, status)
        self.assertEqual(event.last_error, last_error)

    def create_contact_event(self, data: ContactEventData):
        return DatamailerContactEvent.objects.create(
            event_id=data.event_id,
            event_type=data.event_type,
            email=data.email,
            client="dtc-courses",
            audience=data.audience,
            duplicate_count=data.duplicate_count,
        )

    def test_datamailer_operations_non_staff_denied(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(self.datamailer_operations_url())

        self.assertEqual(response.status_code, 302)

    def test_datamailer_operations_staff_allowed(self):
        self.create_datamailer_operations_records()

        self.login_admin()
        response = self.client.get(self.datamailer_operations_url())

        self.assertEqual(response.status_code, 200)
        self.assert_datamailer_operations_content(response)
        self.assert_datamailer_send_totals(response)

    def test_datamailer_operations_requeues_failed_and_dead_outbox_events(self):
        events = self.create_requeue_outbox_events()

        response = self.post_datamailer_requeue()

        self.assertRedirects(response, self.datamailer_operations_url())
        self.assert_outbox_event_requeued(events["failed"])
        self.assert_outbox_event_requeued(events["dead"])
        self.assert_outbox_event_unchanged(
            events["acked"],
            DatamailerOutboxStatus.ACKED,
            "old error",
        )

    def test_datamailer_events_non_staff_denied(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(self.datamailer_events_url())

        self.assertEqual(response.status_code, 302)

    def test_datamailer_events_staff_allowed(self):
        hard_bounce = ContactEventData(
            event_id="evt-hard-bounce",
            event_type="contact.hard_bounced",
            email="student@example.com",
            audience="ml-zoomcamp",
            duplicate_count=2,
        )
        self.create_contact_event(hard_bounce)
        opened = ContactEventData(
            event_id="evt-opened",
            event_type="message.opened",
            email="other@example.com",
        )
        self.create_contact_event(opened)

        self.login_admin()
        response = self.client.get(self.datamailer_events_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datamailer events")
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "contact.hard_bounced")
        self.assertContains(response, "ml-zoomcamp")
        self.assertEqual(response.context["metrics"]["total"], 2)
        self.assertEqual(response.context["metrics"]["duplicates"], 2)

    def test_datamailer_events_filters_by_type_and_search(self):
        hard_bounce = ContactEventData(
            event_id="evt-hard-bounce",
            event_type="contact.hard_bounced",
            email="student@example.com",
            audience="ml-zoomcamp",
        )
        self.create_contact_event(hard_bounce)
        opened = ContactEventData(
            event_id="evt-opened",
            event_type="message.opened",
            email="other@example.com",
        )
        self.create_contact_event(opened)

        self.login_admin()
        response = self.client.get(
            self.datamailer_events_url(),
            {"event_type": "contact.hard_bounced", "q": "student"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student@example.com")
        self.assertNotContains(response, "other@example.com")
        self.assertEqual(
            response.context["selected_event_type"],
            "contact.hard_bounced",
        )
        self.assertEqual(response.context["search_query"], "student")
