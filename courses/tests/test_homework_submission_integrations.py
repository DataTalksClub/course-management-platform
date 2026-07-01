from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Project,
    ProjectState,
    ProjectSubmission,
    Question,
    QuestionTypes,
    Submission,
    User,
)
from courses.views.homework_learning_links import (
    find_duplicate_learning_in_public_links,
)


class HomeworkSubmissionIntegrationTest(TestCase):
    def setUp(self):
        self.user = self.create_student()
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.enable_homework_comments()
        self.homework = self.create_homework()
        self.create_questions()
        self.client.force_login(self.user)

    def create_student(self):
        return User.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

    def create_course(self):
        return Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def enable_homework_comments(self):
        self.course.homework_problems_comments_field = True
        self.course.save()

    def create_homework(self):
        return Homework.objects.create(
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

    def create_questions(self):
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

    def homework_url(self):
        return reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

    def confirmation_post_data(self):
        return {
            f"answer_{self.multiple_choice_question.id}": ["2"],
            f"answer_{self.free_form_question.id}": [
                "I used pandas and DuckDB."
            ],
            f"answer_{self.checkbox_question.id}": ["1", "3"],
            "learning_in_public_links[]": ["https://example.com/post"],
            "time_spent_lectures": "2.5",
            "time_spent_homework": "4",
            "problems_comments": "No blockers.",
            "faq_contribution_url": (
                "https://github.com/DataTalksClub/faq/pull/1"
            ),
        }

    def post_homework(self, post_data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                self.homework_url(),
                post_data,
                HTTP_HOST="localhost",
            )

    def get_submission(self):
        return Submission.objects.get(
            student=self.user,
            homework=self.homework,
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="project",
            title="Project",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def create_project_submission(self, learning_links):
        project = self.create_project()
        return ProjectSubmission.objects.create(
            project=project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            learning_in_public_links=learning_links,
        )

    def assert_confirmation_payload_basics(
        self, payload, submission
    ):
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
            payload["metadata"]["event"],
            "homework_submission",
        )

    def assert_confirmation_context(self, payload, submission):
        context = payload["context"]
        self.assertEqual(context["submission_id"], submission.id)
        self.assertEqual(
            context["update_url"],
            "http://localhost/course/homework/hw1",
        )
        self.assertEqual(
            context["profile_url"],
            "http://localhost/accounts/settings/",
        )
        self.assertEqual(
            context["notification_category"],
            "homework and project submissions",
        )
        self.assertIn(
            "homework and project submission emails",
            context["notification_footer_text"],
        )
        self.assertEqual(
            context["intro_text"],
            "Your homework submission for Homework 1 in Course was saved.",
        )

    def expected_learning_in_public_field(self):
        return {
            "key": "learning_in_public_links",
            "label": "Learning in public links",
            "value": "https://example.com/post",
            "values": ["https://example.com/post"],
        }

    def expected_lecture_time_field(self):
        return {
            "key": "time_spent_lectures",
            "label": "Time spent on lectures",
            "value": "2.5 hours",
        }

    def expected_homework_time_field(self):
        return {
            "key": "time_spent_homework",
            "label": "Time spent on homework",
            "value": "4 hours",
        }

    def expected_problem_comments_field(self):
        return {
            "key": "problems_comments",
            "label": "Problems, comments, or feedback",
            "value": "No blockers.",
        }

    def expected_faq_contribution_field(self):
        return {
            "key": "faq_contribution_url",
            "label": "FAQ contribution URL",
            "value": "https://github.com/DataTalksClub/faq/pull/1",
        }

    def expected_submission_fields(self):
        fields = []
        field = self.expected_learning_in_public_field()
        fields.append(field)
        field = self.expected_lecture_time_field()
        fields.append(field)
        field = self.expected_homework_time_field()
        fields.append(field)
        field = self.expected_problem_comments_field()
        fields.append(field)
        field = self.expected_faq_contribution_field()
        fields.append(field)
        return fields

    def assert_submission_fields(self, payload):
        self.assertEqual(
            payload["context"]["submission_fields"],
            self.expected_submission_fields(),
        )

    def multiple_choice_answer_record(self):
        selected_options = [{"index": 2, "value": "Second option"}]
        return {
            "question_id": self.multiple_choice_question.id,
            "question": "Pick one option",
            "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
            "answer": "2. Second option",
            "raw_answer": "2",
            "selected_options": selected_options,
        }

    def free_form_answer_record(self):
        return {
            "question_id": self.free_form_question.id,
            "question": "Explain your approach",
            "question_type": QuestionTypes.FREE_FORM.value,
            "answer": "I used pandas and DuckDB.",
            "raw_answer": "I used pandas and DuckDB.",
            "selected_options": [],
        }

    def checkbox_answer_record(self):
        selected_options = [
            {"index": 1, "value": "Alpha"},
            {"index": 3, "value": "Gamma"},
        ]
        return {
            "question_id": self.checkbox_question.id,
            "question": "Pick all matching options",
            "question_type": QuestionTypes.CHECKBOXES.value,
            "answer": "1. Alpha, 3. Gamma",
            "raw_answer": "1,3",
            "selected_options": selected_options,
        }

    def submitted_answer_records(self):
        multiple_choice_answer = self.multiple_choice_answer_record()
        free_form_answer = self.free_form_answer_record()
        checkbox_answer = self.checkbox_answer_record()
        return [
            multiple_choice_answer,
            free_form_answer,
            checkbox_answer,
        ]

    def assert_submitted_answers(self, payload):
        expected_answers = self.submitted_answer_records()
        self.assertEqual(
            payload["context"]["submitted_answers"],
            expected_answers,
        )

    def assert_confirmation_summary(self, payload):
        self.assertIn(
            "Time spent on lectures: 2.5 hours",
            payload["context"]["submission_summary_text"],
        )
        self.assertIn(
            "Pick all matching options: 1. Alpha, 3. Gamma",
            payload["context"]["submitted_answers_text"],
        )

    @override_settings(PUBLIC_BASE_URL="")
    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_homework_submission_sends_confirmation_email(
        self,
        send_email,
    ):
        response = self.post_homework(self.confirmation_post_data())

        self.assertEqual(response.status_code, 302)
        submission = self.get_submission()
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]

        self.assert_confirmation_payload_basics(payload, submission)
        self.assert_confirmation_context(payload, submission)
        self.assert_submission_fields(payload)
        self.assert_submitted_answers(payload)
        self.assert_confirmation_summary(payload)

    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_homework_submission_uses_datamailer_without_local_preference(
        self,
        send_email,
    ):
        post_data = self.datamailer_preference_post_data()

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        self.assert_submission_exists()
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["category_tag"], "submission-results")

    def datamailer_preference_post_data(self):
        answer_key = f"answer_{self.multiple_choice_question.id}"
        return {
            answer_key: ["2"],
            "learning_in_public_links[]": [],
        }

    def assert_submission_exists(self):
        self.assertTrue(
            Submission.objects.filter(
                student=self.user,
                homework=self.homework,
            ).exists()
        )

    @override_settings(PUBLIC_BASE_URL="https://dev.courses.datatalks.club")
    @patch("courses.views.homework_confirmation.send_transactional_email")
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

    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_reused_learning_in_public_link_is_rejected(
        self,
        send_email,
    ):
        self.create_previous_homework_submission_with_learning_link()

        post_data = self.reused_learning_link_post_data()
        url = self.homework_url()
        response = self.client.post(url, post_data)

        self.assert_reused_learning_link_rejected(response)
        self.assert_current_homework_not_submitted()
        send_email.assert_not_called()

    def create_previous_homework_submission_with_learning_link(self):
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

    def reused_learning_link_post_data(self):
        return {
            "learning_in_public_links[]": ["https://example.com/post"]
        }

    def assert_reused_learning_link_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links were already used",
        )

    def assert_current_homework_not_submitted(self):
        self.assertFalse(
            Submission.objects.filter(
                student=self.user,
                homework=self.homework,
            ).exists()
        )

    def test_duplicate_learning_in_public_finder_checks_project_submissions(
        self,
    ):
        self.create_project_submission(
            ["https://example.com/project-post"]
        )

        duplicate_links = find_duplicate_learning_in_public_links(
            user=self.user,
            course=self.course,
            links=[
                "https://example.com/new-post",
                "https://example.com/project-post",
            ],
            current_submission=None,
        )

        self.assertEqual(
            duplicate_links,
            ["https://example.com/project-post"],
        )
