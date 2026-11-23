from unittest import mock

from django.test import Client
from django.urls import reverse

from accounts.models import CustomUser
from api.tests.homework_api_base import HomeworkAPITestBase
from course_management.datamailer.sync.score_notifications import (
    queue_homework_score_notification,
)
from courses.models.homework import HomeworkState
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)


QUEUE_PATH = (
    "api.views.homework_score_notifications."
    "queue_homework_score_notification"
)


class HomeworkNotifyScoresAPITestCase(HomeworkAPITestBase):
    def setUp(self):
        super().setUp()
        self.homework = self._create_homework(
            slug="hw4",
            state=HomeworkState.CLOSED.value,
        )
        self.url = (
            f"/api/courses/{self.course.slug}/homeworks/by-slug/"
            f"{self.homework.slug}/notify-scores/"
        )

    @property
    def idempotency_key(self):
        return f"homework-score:{self.course.slug}:{self.homework.slug}"

    def _mark_scored(self):
        self.homework.state = HomeworkState.SCORED.value
        self.homework.save(update_fields=["state"])

    def test_get_empty_is_read_only_and_works_in_any_state(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "idempotency_key": self.idempotency_key,
                "sent": False,
                "audit": None,
            },
        )
        self.assertFalse(DatamailerSendAudit.objects.exists())
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    def test_get_after_cadmin_send_shows_sent_without_writing(self):
        """The hw4 case: cadmin already sent, the worker wrote the audit."""
        self._mark_scored()
        DatamailerOutboxEvent.objects.create(
            event_id="cadmin-hw-score-event",
            event_type="homework.score_notification",
            idempotency_key=self.idempotency_key,
            status=DatamailerOutboxStatus.ACKED,
            payload={"homework_id": self.homework.pk},
        )
        audit = DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key=self.idempotency_key,
            template_key="homework-score-notification",
            enqueued_count=171,
            skipped_count=5,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["sent"])
        self.assertEqual(data["audit"]["status"], "succeeded")
        self.assertEqual(data["audit"]["enqueued_count"], 171)
        self.assertEqual(data["audit"]["skipped_count"], 5)
        self.assertEqual(DatamailerSendAudit.objects.count(), 1)
        self.assertEqual(DatamailerOutboxEvent.objects.count(), 1)
        audit.refresh_from_db()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)

    def test_post_queues_and_returns_pending_audit(self):
        self._mark_scored()

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_homework_score_notification,
        ) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        queue.assert_called_once_with(self.homework)
        data = response.json()
        self.assertEqual(data["idempotency_key"], self.idempotency_key)
        self.assertFalse(data["sent"])
        self.assertEqual(data["audit"]["status"], "pending")
        self.assertEqual(data["audit"]["template_key"], "homework-score-notification")
        event = DatamailerOutboxEvent.objects.get(
            idempotency_key=self.idempotency_key,
        )
        self.assertEqual(event.event_type, "homework.score_notification")
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)

    def test_second_post_does_not_queue_again(self):
        self._mark_scored()

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_homework_score_notification,
        ) as queue:
            first = self.client.post(self.url)
            second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        queue.assert_called_once_with(self.homework)
        self.assertEqual(
            second.json()["code"],
            "homework_score_notification_already_queued",
        )
        self.assertEqual(DatamailerOutboxEvent.objects.count(), 1)

    def test_post_after_cadmin_succeeded_audit_returns_409(self):
        self._mark_scored()
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key=self.idempotency_key,
            template_key="homework-score-notification",
            enqueued_count=171,
            skipped_count=5,
        )

        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        queue.assert_not_called()
        data = response.json()
        self.assertTrue(data["sent"])
        self.assertEqual(data["audit"]["enqueued_count"], 171)
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    def test_post_after_cadmin_button_click_does_not_queue_again(self):
        """Click the real cadmin button, then call the API."""
        self._mark_scored()
        staff = CustomUser.objects.create_user(
            username="cadmin-staff",
            email="cadmin-staff@example.com",
            password="password",
            is_staff=True,
        )
        browser = Client()
        browser.force_login(staff)
        with mock.patch(
            "cadmin.views.homework.check_relay_availability",
            return_value=(True, ""),
        ):
            browser.post(
                reverse(
                    "cadmin_homework_notify_scores",
                    kwargs={
                        "course_slug": self.course.slug,
                        "homework_slug": self.homework.slug,
                    },
                )
            )
        self.assertEqual(
            DatamailerOutboxEvent.objects.filter(
                idempotency_key=self.idempotency_key,
            ).count(),
            1,
        )

        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        queue.assert_not_called()
        self.assertEqual(response.json()["audit"]["status"], "pending")
        self.assertEqual(
            DatamailerOutboxEvent.objects.filter(
                idempotency_key=self.idempotency_key,
            ).count(),
            1,
        )

    def test_post_after_acked_cadmin_event_without_audit_returns_409(self):
        self._mark_scored()
        DatamailerOutboxEvent.objects.create(
            event_id="cadmin-hw-score-acked",
            event_type="homework.score_notification",
            idempotency_key=self.idempotency_key,
            status=DatamailerOutboxStatus.ACKED,
            payload={"homework_id": self.homework.pk},
            response_payload={"enqueued_count": 171},
        )

        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 409)
        queue.assert_not_called()
        data = response.json()
        self.assertTrue(data["sent"])
        self.assertEqual(data["audit"]["enqueued_count"], 171)

    def test_post_requires_scored_state(self):
        with mock.patch(QUEUE_PATH) as queue:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "homework_not_scored")
        queue.assert_not_called()
        self.assertFalse(DatamailerSendAudit.objects.exists())
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    def test_queue_failure_returns_502_and_allows_retry(self):
        self._mark_scored()

        with mock.patch(QUEUE_PATH, side_effect=RuntimeError("queue down")):
            failed = self.client.post(self.url)

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(failed.json()["audit"]["status"], "failed")

        with mock.patch(
            QUEUE_PATH,
            wraps=queue_homework_score_notification,
        ) as queue:
            retried = self.client.post(self.url)

        self.assertEqual(retried.status_code, 200)
        queue.assert_called_once_with(self.homework)
        self.assertEqual(retried.json()["audit"]["status"], "pending")

    def test_unknown_homework_is_404(self):
        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/"
            "missing/notify-scores/"
        )
        self.assertEqual(response.status_code, 404)

    def test_staff_token_is_required(self):
        unauthenticated = Client()
        non_staff = self._non_staff_client("hw-notify-scores-nonstaff")

        self.assertEqual(unauthenticated.get(self.url).status_code, 401)
        self.assertEqual(unauthenticated.post(self.url).status_code, 401)
        self._assert_staff_token_required(non_staff.get(self.url))
        self._assert_staff_token_required(non_staff.post(self.url))
