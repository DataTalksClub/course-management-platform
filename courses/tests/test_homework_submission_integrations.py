from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Submission,
    User,
)


class HomeworkSubmissionIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )
        self.course = Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now(),
            homework_url_field=False,
            time_spent_lectures_field=False,
            time_spent_homework_field=False,
            faq_contribution_field=False,
            learning_in_public_cap=2,
        )
        self.client.force_login(self.user)

    @patch("courses.views.homework.send_transactional_email")
    def test_homework_submission_sends_confirmation_email(self, send_email):
        url = reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {"learning_in_public_links[]": ["https://example.com/post"]},
            )

        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(
            student=self.user,
            homework=self.homework,
        )
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(
            payload["template_key"],
            "homework-submission-confirmation",
        )
        self.assertEqual(
            payload["idempotency_key"],
            (
                f"homework-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
        )
        self.assertEqual(
            payload["context"]["submission_id"],
            submission.id,
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "homework_submission",
        )

    @patch("courses.views.homework.send_transactional_email")
    def test_reused_learning_in_public_link_is_rejected(self, send_email):
        previous_homework = Homework.objects.create(
            course=self.course,
            slug="hw0",
            title="Homework 0",
            due_date=timezone.now(),
        )
        Submission.objects.create(
            homework=previous_homework,
            student=self.user,
            enrollment=self.enrollment,
            learning_in_public_links=["https://example.com/post"],
        )
        url = reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

        response = self.client.post(
            url,
            {"learning_in_public_links[]": ["https://example.com/post"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links were already used",
        )
        self.assertFalse(
            Submission.objects.filter(
                student=self.user,
                homework=self.homework,
            ).exists()
        )
        send_email.assert_not_called()
