from datetime import timedelta
from unittest import mock

import requests
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, Token
from course_management.datamailer.sync.audit import (
    DatamailerSendAuditData,
    record_datamailer_send_audit,
)
from courses.models import Course, Project
from courses.models.project import ProjectState
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

SEND_AUDITS_URL = "/api/datamailer/send-audits"
CLIENT_PATH = "course_management.datamailer.send_audit_skips.DatamailerClient"
KEY = "peer-review-assignment:test-course:proj1"
RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "test-key",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
}


class FakeTransactional:
    """Read-only Relay API double; any send attempt fails the test."""

    def __init__(self, pages, statuses):
        self.pages = list(pages)
        self.statuses = statuses
        self.since_calls = []
        self.status_calls = []

    def transactional_messages_since(self, since):
        self.since_calls.append(since)
        if not self.pages:
            return {"messages": []}
        return self.pages.pop(0)

    def transactional_message_status(self, message_id):
        self.status_calls.append(message_id)
        return {"message": self.statuses[message_id], "events": []}


class FakeClient:
    def __init__(self, transactional):
        self.transactional = transactional


class SkippedRecipientsAPITestCase(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create(
            username="staff", email="staff@example.com", is_staff=True
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = Client(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.learner = CustomUser.objects.create(
            username="learner", email="learner@example.com"
        )
        self.other = CustomUser.objects.create(
            username="other", email="Other@Example.com"
        )
        self.course = Course.objects.create(slug="test-course", title="T")
        self.project = Project.objects.create(
            course=self.course,
            slug="proj1",
            title="Project 1",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=ProjectState.PEER_REVIEWING.value,
        )
        self.notify_url = (
            "/api/courses/test-course/projects/by-slug/proj1/"
            "notify-peer-reviews/"
        )

    def _record_with_relay_skips(self):
        response = {
            "created_count": 3,
            "enqueued_count": 1,
            "skipped_count": 2,
            "idempotent_replay_count": 0,
            "skipped": [
                {
                    "message_id": 14699,
                    "contact_id": 325,
                    "email": "learner@example.com",
                    "source_object_key": f"user:{self.learner.pk}",
                    "reason": "category_unsubscribe",
                },
                {
                    "message_id": 14700,
                    "contact_id": 326,
                    "email": "other@example.com",
                    "source_object_key": "enrollment:99",
                    "reason": "hard_bounce",
                },
            ],
        }
        return record_datamailer_send_audit(
            DatamailerSendAuditData(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                payload={
                    "idempotency_key": KEY,
                    "template_key": "peer-review-assignment",
                },
                list_key="test-course:@e:@project:proj1",
                response=response,
            )
        )

    def _legacy_audit(self):
        # Sent before Relay returned per-member skip reasons.
        return DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key=KEY,
            template_key="peer-review-assignment",
            created_count=3,
            enqueued_count=2,
            skipped_count=1,
            response_payload={"skipped_count": 1, "enqueued_count": 2},
            occurred_at=timezone.now(),
        )

    def _expected_persisted(self):
        return [
            {
                "user_id": self.learner.pk,
                "email": "learner@example.com",
                "reason": "category_unsubscribe",
                "source_object_key": f"user:{self.learner.pk}",
                "relay_message_id": 14699,
                "relay_contact_id": 325,
            },
            {
                "user_id": self.other.pk,
                "email": "other@example.com",
                "reason": "hard_bounce",
                "source_object_key": "enrollment:99",
                "relay_message_id": 14700,
                "relay_contact_id": 326,
            },
        ]

    def _fake_lookup(self):
        prefix = f"{KEY}:"
        pages = [
            {
                "messages": [
                    {"id": "14698", "client_reference": f"{prefix}user:1",
                     "status": "queued", "updated_at": "x"},
                    {"id": "14699",
                     "client_reference": f"{prefix}user:{self.learner.pk}",
                     "status": "suppressed", "updated_at": "x"},
                    {"id": "999", "client_reference": "other-key:user:5",
                     "status": "suppressed", "updated_at": "x"},
                ]
            }
        ]
        statuses = {
            14699: {
                "id": 14699,
                "email": "learner@example.com",
                "contact_id": 325,
                "status": "skipped",
                "last_error": "category_unsubscribe",
            }
        }
        return FakeTransactional(pages, statuses)

    def test_list_returns_persisted_skips_with_user_ids(self):
        audit = self._record_with_relay_skips()

        with mock.patch(CLIENT_PATH) as relay:
            response = self.client.get(
                SEND_AUDITS_URL, {"idempotency_key": KEY}
            )

        relay.assert_not_called()
        self.assertEqual(response.status_code, 200)
        item = response.json()["audits"][0]
        self.assertEqual(item["id"], audit.pk)
        self.assertEqual(item["skipped_recipients_source"], "audit")
        self.assertEqual(
            item["skipped_recipients"], self._expected_persisted()
        )

    def test_list_never_calls_relay_for_legacy_audit(self):
        self._legacy_audit()

        with mock.patch(CLIENT_PATH) as relay:
            response = self.client.get(
                SEND_AUDITS_URL, {"idempotency_key": KEY}
            )

        relay.assert_not_called()
        item = response.json()["audits"][0]
        self.assertEqual(item["skipped_recipients_source"], "not_recorded")
        self.assertEqual(item["skipped_recipients"], [])

    def test_detail_returns_persisted_skips(self):
        audit = self._record_with_relay_skips()

        response = self.client.get(f"{SEND_AUDITS_URL}/{audit.pk}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], audit.pk)
        self.assertEqual(data["skipped_recipients"], self._expected_persisted())

    @override_settings(**RELAY_SETTINGS)
    def test_detail_looks_up_legacy_skips_read_only(self):
        audit = self._legacy_audit()
        fake = self._fake_lookup()

        with mock.patch(CLIENT_PATH, return_value=FakeClient(fake)):
            response = self.client.get(f"{SEND_AUDITS_URL}/{audit.pk}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["skipped_recipients_source"], "relay_lookup")
        self.assertEqual(
            data["skipped_recipients"],
            [
                {
                    "user_id": self.learner.pk,
                    "email": "learner@example.com",
                    "reason": "category_unsubscribe",
                    "source_object_key": f"user:{self.learner.pk}",
                    "relay_message_id": 14699,
                    "relay_contact_id": 325,
                }
            ],
        )
        self.assertEqual(fake.status_calls, [14699])
        since = fake.since_calls[0]
        self.assertLess(since, audit.occurred_at.isoformat())
        self.assertGreater(
            since, (audit.occurred_at - timedelta(hours=1)).isoformat()
        )
        # The audit row is not modified by a read.
        audit.refresh_from_db()
        self.assertNotIn("skipped", audit.response_payload)

    @override_settings(**RELAY_SETTINGS)
    def test_detail_reports_unavailable_when_relay_lookup_fails(self):
        audit = self._legacy_audit()
        fake = self._fake_lookup()
        fake.transactional_messages_since = mock.Mock(
            side_effect=requests.ConnectionError("down")
        )

        with mock.patch(CLIENT_PATH, return_value=FakeClient(fake)):
            response = self.client.get(f"{SEND_AUDITS_URL}/{audit.pk}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["skipped_recipients_source"], "unavailable")
        self.assertEqual(data["skipped_recipients"], [])

    def test_detail_without_relay_config_reports_unavailable(self):
        audit = self._legacy_audit()

        response = self.client.get(f"{SEND_AUDITS_URL}/{audit.pk}")

        self.assertEqual(
            response.json()["skipped_recipients_source"], "unavailable"
        )

    def test_detail_unknown_audit_is_404(self):
        response = self.client.get(f"{SEND_AUDITS_URL}/999999")

        self.assertEqual(response.status_code, 404)

    def test_audit_without_skips_reports_none(self):
        audit = DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key=KEY,
            enqueued_count=3,
        )

        with mock.patch(CLIENT_PATH) as relay:
            response = self.client.get(f"{SEND_AUDITS_URL}/{audit.pk}")

        relay.assert_not_called()
        data = response.json()
        self.assertIsNone(data["skipped_recipients_source"])
        self.assertEqual(data["skipped_recipients"], [])

    @override_settings(**RELAY_SETTINGS)
    def test_notify_status_includes_skipped_recipients(self):
        self._legacy_audit()
        fake = self._fake_lookup()

        with mock.patch(CLIENT_PATH, return_value=FakeClient(fake)):
            response = self.client.get(self.notify_url)

        self.assertEqual(response.status_code, 200)
        audit = response.json()["audit"]
        self.assertEqual(audit["skipped_count"], 1)
        self.assertEqual(audit["skipped_recipients_source"], "relay_lookup")
        self.assertEqual(
            audit["skipped_recipients"][0]["email"], "learner@example.com"
        )
        self.assertEqual(
            audit["skipped_recipients"][0]["reason"], "category_unsubscribe"
        )

    def test_skip_details_require_staff_token(self):
        audit = self._record_with_relay_skips()
        user_token = Token.objects.create(user=self.learner)
        non_staff = Client(HTTP_AUTHORIZATION=f"Token {user_token.key}")
        anonymous = Client()

        for url in (
            SEND_AUDITS_URL,
            f"{SEND_AUDITS_URL}/{audit.pk}",
            self.notify_url,
        ):
            with self.subTest(url=url):
                forbidden = non_staff.get(url)
                self.assertEqual(forbidden.status_code, 403)
                self.assertNotIn(b"learner@example.com", forbidden.content)
                unauthenticated = anonymous.get(url)
                self.assertEqual(unauthenticated.status_code, 401)
                self.assertNotIn(
                    b"learner@example.com", unauthenticated.content
                )
