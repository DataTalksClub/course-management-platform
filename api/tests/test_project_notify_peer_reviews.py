from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import Client

from accounts.models import CustomUser, Token
from api.tests.project_api_base import ProjectAPITestBase
from course_management.datamailer.sync.audit import (
    DatamailerSendAuditData,
    record_datamailer_send_audit,
)
from courses.models.project import ProjectState
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

SEND_PATH = (
    "course_management.datamailer.sync.peer_review_send_once."
    "send_peer_review_assignment_notification"
)
IDEMPOTENCY_KEY = "peer-review-assignment:test-course:proj1"


def _record_succeeded_send(project):
    payload = {
        "idempotency_key": (
            f"peer-review-assignment:{project.course.slug}:{project.slug}"
        ),
        "template_key": "peer-review-assignment",
        "metadata": {"source": "course-management-platform"},
    }
    record_datamailer_send_audit(
        DatamailerSendAuditData(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key="project-submitters:test-course:proj1",
            response={"enqueued_count": 3, "created_count": 3},
        )
    )
    return {"enqueued_count": 3}


def _record_failed_send(project):
    payload = {
        "idempotency_key": (
            f"peer-review-assignment:{project.course.slug}:{project.slug}"
        ),
        "template_key": "peer-review-assignment",
    }
    record_datamailer_send_audit(
        DatamailerSendAuditData(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key="project-submitters:test-course:proj1",
            error="Relay unavailable",
        )
    )


class ProjectNotifyPeerReviewsAPITestCase(ProjectAPITestBase):
    def setUp(self):
        super().setUp()
        self.project = self._create_project(
            state=ProjectState.PEER_REVIEWING.value
        )
        self.url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            f"{self.project.slug}/notify-peer-reviews/"
        )

    def _audit(self):
        return DatamailerSendAudit.objects.get(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=IDEMPOTENCY_KEY,
        )

    def test_post_sends_once_and_returns_send_audit(self):
        with mock.patch(SEND_PATH, side_effect=_record_succeeded_send) as send:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0].pk, self.project.pk)
        data = response.json()
        self.assertEqual(data["idempotency_key"], IDEMPOTENCY_KEY)
        self.assertTrue(data["sent"])
        audit = data["audit"]
        self.assertEqual(audit["status"], DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit["enqueued_count"], 3)
        self.assertEqual(audit["idempotency_key"], IDEMPOTENCY_KEY)
        for field in ("occurred_at", "created_at", "updated_at"):
            self.assertTrue(audit[field])

    def test_second_post_is_refused_with_existing_audit(self):
        with mock.patch(SEND_PATH, side_effect=_record_succeeded_send) as send:
            first = self.client.post(self.url)
            second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(send.call_count, 1)
        data = second.json()
        self.assertEqual(data["code"], "peer_review_notification_already_sent")
        self.assertEqual(
            data["audit"]["status"], DatamailerSendAuditStatus.SUCCEEDED
        )
        self.assertEqual(data["audit"]["enqueued_count"], 3)

    def test_post_refused_after_cadmin_send_with_same_key(self):
        _record_succeeded_send(self.project)

        with mock.patch(SEND_PATH) as send:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        send.assert_not_called()

    def test_concurrent_post_during_send_is_refused(self):
        racer_responses = []

        def send_while_racing(project):
            racer_responses.append(self.client.post(self.url))
            return _record_succeeded_send(project)

        with mock.patch(SEND_PATH, side_effect=send_while_racing) as send:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(racer_responses), 1)
        racer = racer_responses[0]
        self.assertEqual(racer.status_code, 409)
        self.assertEqual(
            racer.json()["audit"]["status"],
            DatamailerSendAuditStatus.PENDING,
        )

    def test_failed_send_releases_claim_and_allows_retry(self):
        with mock.patch(SEND_PATH, side_effect=_record_failed_send):
            failed = self.client.post(self.url)

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(
            failed.json()["audit"]["status"],
            DatamailerSendAuditStatus.FAILED,
        )

        with mock.patch(SEND_PATH, side_effect=_record_succeeded_send) as send:
            retry = self.client.post(self.url)

        self.assertEqual(retry.status_code, 200)
        send.assert_called_once()

    def test_send_without_audit_marks_claim_failed(self):
        # e.g. Relay config missing: the send audits a different key.
        with mock.patch(SEND_PATH, return_value=None):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 502)
        audit = self._audit()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertTrue(audit.error)

    def test_send_exception_marks_claim_failed(self):
        with mock.patch(SEND_PATH, side_effect=RuntimeError("boom")):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._audit().status, DatamailerSendAuditStatus.FAILED
        )

    def test_post_requires_peer_reviewing_state(self):
        self.project.state = ProjectState.COLLECTING_SUBMISSIONS.value
        self.project.save()

        with mock.patch(SEND_PATH) as send:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_not_peer_reviewing")
        send.assert_not_called()
        self.assertFalse(DatamailerSendAudit.objects.exists())

    def test_get_reports_none_before_send(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["sent"])
        self.assertIsNone(data["audit"])
        self.assertEqual(data["idempotency_key"], IDEMPOTENCY_KEY)

    def test_get_reports_audit_after_send_without_sending(self):
        _record_succeeded_send(self.project)

        with mock.patch(SEND_PATH) as send:
            response = self.client.get(self.url)

        send.assert_not_called()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["sent"])
        self.assertEqual(
            data["audit"]["status"], DatamailerSendAuditStatus.SUCCEEDED
        )

    def test_unknown_project_returns_404(self):
        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "missing/notify-peer-reviews/"
        )

        self.assertEqual(response.status_code, 404)

    def test_non_staff_token_is_rejected(self):
        user = CustomUser.objects.create(
            username="notify-nonstaff",
            email="notify-nonstaff@example.com",
        )
        token = Token.objects.create(user=user)
        client = Client(HTTP_AUTHORIZATION=f"Token {token.key}")

        with mock.patch(SEND_PATH) as send:
            post = client.post(self.url)
            get = client.get(self.url)

        self.assertEqual(post.status_code, 403)
        self.assertEqual(get.status_code, 403)
        self.assertEqual(post.json()["code"], "staff_token_required")
        send.assert_not_called()
        self.assertFalse(DatamailerSendAudit.objects.exists())

    def test_missing_token_is_rejected(self):
        client = Client()

        with mock.patch(SEND_PATH) as send:
            post = client.post(self.url)
            get = client.get(self.url)

        self.assertEqual(post.status_code, 401)
        self.assertEqual(get.status_code, 401)
        send.assert_not_called()

    def test_reset_marker_allows_deliberate_resend(self):
        _record_succeeded_send(self.project)

        with self.assertRaises(CommandError):
            call_command(
                "reset_peer_review_notification_marker",
                self.course.slug,
                self.project.slug,
                stdout=StringIO(),
            )
        self.assertEqual(
            self._audit().status, DatamailerSendAuditStatus.SUCCEEDED
        )

        call_command(
            "reset_peer_review_notification_marker",
            self.course.slug,
            self.project.slug,
            "--confirm",
            stdout=StringIO(),
        )
        audit = self._audit()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertIn("reset", audit.error)

        with mock.patch(SEND_PATH, side_effect=_record_succeeded_send) as send:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
