from unittest import mock

from django.test import Client

from api.tests.project_api_base import ProjectAPITestBase
from course_management.datamailer.sync.score_notifications import (
    queue_project_score_notification,
)
from courses.models.project import ProjectState
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)


QUEUE_PATH = "api.views.project_score_notifications.queue_project_score_notification"


class ProjectNotifyScoresAPITestCase(ProjectAPITestBase):
    def setUp(self):
        super().setUp()
        self.project = self._create_project(
            state=ProjectState.CLOSED.value,
        )
        self.url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            f"{self.project.slug}/notify-scores/"
        )

    @property
    def idempotency_key(self):
        return f"project-score:{self.course.slug}:{self.project.slug}"

    def _audit(self, status=DatamailerSendAuditStatus.SUCCEEDED):
        return DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=status,
            idempotency_key=self.idempotency_key,
            template_key="project-score-notification",
            enqueued_count=3 if status == DatamailerSendAuditStatus.SUCCEEDED else 0,
        )

    def test_get_empty_is_read_only_and_does_not_require_completed_state(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "idempotency_key": self.idempotency_key,
                "sent": False,
                "audit": None,
            },
        )
        self.assertFalse(DatamailerSendAudit.objects.exists())
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    def test_post_queues_and_returns_pending_audit(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_project_score_notification,
        ) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        queue.assert_called_once_with(self.project)
        data = response.json()
        self.assertEqual(data["idempotency_key"], self.idempotency_key)
        self.assertFalse(data["sent"])
        self.assertEqual(data["audit"]["status"], "pending")
        self.assertEqual(data["audit"]["idempotency_key"], self.idempotency_key)
        event = DatamailerOutboxEvent.objects.get(
            idempotency_key=self.idempotency_key,
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)

    def test_second_post_returns_existing_audit_without_queueing_again(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_project_score_notification,
        ) as queue:
            first = self.client.post(self.url)
            second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        queue.assert_called_once_with(self.project)
        data = second.json()
        self.assertEqual(data["code"], "project_score_notification_already_queued")
        self.assertEqual(data["audit"]["status"], "pending")

    def test_post_after_cadmin_send_returns_existing_audit(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self._audit()

        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        queue.assert_not_called()
        data = response.json()
        self.assertTrue(data["sent"])
        self.assertEqual(data["audit"]["status"], "succeeded")
        self.assertEqual(data["audit"]["enqueued_count"], 3)

    def test_post_after_cadmin_queued_event_does_not_enqueue_again(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        DatamailerOutboxEvent.objects.create(
            event_id="cadmin-score-event",
            event_type="project.score_notification",
            idempotency_key=self.idempotency_key,
            status=DatamailerOutboxStatus.PENDING,
            payload={"project_id": self.project.pk},
        )

        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        queue.assert_not_called()
        self.assertEqual(response.json()["audit"]["status"], "pending")

    def test_post_requires_completed_state(self):
        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_not_completed")
        queue.assert_not_called()
        self.assertFalse(DatamailerSendAudit.objects.exists())
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    def test_queue_failure_returns_502_and_allows_retry(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])

        with mock.patch(QUEUE_PATH, side_effect=RuntimeError("queue down")):
            failed = self.client.post(self.url)

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(failed.json()["audit"]["status"], "failed")

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_project_score_notification,
        ) as queue:
            retried = self.client.post(self.url)

        self.assertEqual(retried.status_code, 200)
        queue.assert_called_once_with(self.project)
        self.assertEqual(retried.json()["audit"]["status"], "pending")

    def test_staff_token_is_required(self):
        unauthenticated = Client()
        non_staff = self._non_staff_client("notify-scores-nonstaff")

        get_missing = unauthenticated.get(self.url)
        post_missing = unauthenticated.post(self.url)
        get_non_staff = non_staff.get(self.url)
        post_non_staff = non_staff.post(self.url)

        self.assertEqual(get_missing.status_code, 401)
        self.assertEqual(post_missing.status_code, 401)
        self.assertEqual(get_non_staff.status_code, 403)
        self.assertEqual(post_non_staff.status_code, 403)
        self.assertEqual(get_non_staff.json()["code"], "staff_token_required")
        self.assertEqual(post_non_staff.json()["code"], "staff_token_required")
