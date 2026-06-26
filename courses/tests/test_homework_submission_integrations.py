from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Question,
    QuestionTypes,
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
        self.course.homework_problems_comments_field = True
        self.course.save()
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now(),
            homework_url_field=False,
            time_spent_lectures_field=True,
            time_spent_homework_field=True,
            faq_contribution_field=True,
            learning_in_public_cap=2,
        )
        self.multiple_choice_question = Question.objects.create(
            homework=self.homework,
            text="Pick one option",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="First option\nSecond option",
        )
        self.free_form_question = Question.objects.create(
            homework=self.homework,
            text="Explain your approach",
            question_type=QuestionTypes.FREE_FORM.value,
        )
        self.checkbox_question = Question.objects.create(
            homework=self.homework,
            text="Pick all matching options",
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers="Alpha\nBeta\nGamma",
        )
        self.client.force_login(self.user)

    @override_settings(PUBLIC_BASE_URL="")
    @patch("courses.views.homework.send_transactional_email")
    def test_homework_submission_sends_confirmation_email(
        self,
        send_email,
    ):
        url = reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    f"answer_{self.multiple_choice_question.id}": ["2"],
                    f"answer_{self.free_form_question.id}": [
                        "I used pandas and DuckDB."
                    ],
                    f"answer_{self.checkbox_question.id}": ["1", "3"],
                    "learning_in_public_links[]": [
                        "https://example.com/post"
                    ],
                    "time_spent_lectures": "2.5",
                    "time_spent_homework": "4",
                    "problems_comments": "No blockers.",
                    "faq_contribution_url": (
                        "https://github.com/DataTalksClub/faq/pull/1"
                    ),
                },
                HTTP_HOST="localhost",
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
        self.assertEqual(payload["category_tag"], "submission-results")
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
            payload["context"]["update_url"],
            "http://localhost/course/homework/hw1",
        )
        self.assertEqual(
            payload["context"]["profile_url"],
            "http://localhost/accounts/settings/",
        )
        self.assertEqual(
            payload["context"]["notification_category"],
            "homework and project submissions",
        )
        self.assertIn(
            "homework and project submission emails",
            payload["context"]["notification_footer_text"],
        )
        self.assertEqual(
            payload["context"]["intro_text"],
            (
                "Your homework submission for Homework 1 in Course "
                "was saved."
            ),
        )
        self.assertEqual(
            payload["context"]["submission_fields"],
            [
                {
                    "key": "learning_in_public_links",
                    "label": "Learning in public links",
                    "value": "https://example.com/post",
                    "values": ["https://example.com/post"],
                },
                {
                    "key": "time_spent_lectures",
                    "label": "Time spent on lectures",
                    "value": "2.5 hours",
                },
                {
                    "key": "time_spent_homework",
                    "label": "Time spent on homework",
                    "value": "4 hours",
                },
                {
                    "key": "problems_comments",
                    "label": "Problems, comments, or feedback",
                    "value": "No blockers.",
                },
                {
                    "key": "faq_contribution_url",
                    "label": "FAQ contribution URL",
                    "value": (
                        "https://github.com/DataTalksClub/faq/pull/1"
                    ),
                },
            ],
        )
        self.assertEqual(
            payload["context"]["submitted_answers"],
            [
                {
                    "question_id": self.multiple_choice_question.id,
                    "question": "Pick one option",
                    "question_type": (
                        QuestionTypes.MULTIPLE_CHOICE.value
                    ),
                    "answer": "2. Second option",
                    "raw_answer": "2",
                    "selected_options": [
                        {"index": 2, "value": "Second option"}
                    ],
                },
                {
                    "question_id": self.free_form_question.id,
                    "question": "Explain your approach",
                    "question_type": QuestionTypes.FREE_FORM.value,
                    "answer": "I used pandas and DuckDB.",
                    "raw_answer": "I used pandas and DuckDB.",
                    "selected_options": [],
                },
                {
                    "question_id": self.checkbox_question.id,
                    "question": "Pick all matching options",
                    "question_type": QuestionTypes.CHECKBOXES.value,
                    "answer": "1. Alpha, 3. Gamma",
                    "raw_answer": "1,3",
                    "selected_options": [
                        {"index": 1, "value": "Alpha"},
                        {"index": 3, "value": "Gamma"},
                    ],
                },
            ],
        )
        self.assertIn(
            "Time spent on lectures: 2.5 hours",
            payload["context"]["submission_summary_text"],
        )
        self.assertIn(
            "Pick all matching options: 1. Alpha, 3. Gamma",
            payload["context"]["submitted_answers_text"],
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "homework_submission",
        )

    @patch("courses.views.homework.send_transactional_email")
    def test_homework_submission_skips_confirmation_when_preference_off(
        self,
        send_email,
    ):
        self.user.email_submission_confirmations = False
        self.user.save(update_fields=["email_submission_confirmations"])
        url = reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    f"answer_{self.multiple_choice_question.id}": ["2"],
                    "learning_in_public_links[]": [],
                },
                HTTP_HOST="localhost",
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Submission.objects.filter(
                student=self.user,
                homework=self.homework,
            ).exists()
        )
        send_email.assert_not_called()

    @override_settings(PUBLIC_BASE_URL="https://dev.courses.datatalks.club")
    @patch("courses.views.homework.send_transactional_email")
    def test_homework_confirmation_uses_public_base_url(
        self,
        send_email,
    ):
        url = reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    f"answer_{self.multiple_choice_question.id}": ["1"],
                    "learning_in_public_links[]": [],
                },
                HTTP_HOST="localhost",
            )

        self.assertEqual(response.status_code, 302)
        payload = send_email.call_args.args[0]
        self.assertEqual(
            payload["context"]["update_url"],
            "https://dev.courses.datatalks.club/course/homework/hw1",
        )

    @patch("courses.views.homework.send_transactional_email")
    def test_reused_learning_in_public_link_is_rejected(
        self,
        send_email,
    ):
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
