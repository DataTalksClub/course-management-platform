import logging

from unittest import mock
from django.urls import reverse
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
)


logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
        )

    def project_url(self):
        return reverse("project", args=[self.course.slug, self.project.slug])

    def mock_url_check_status(self, mock_get, mock_head, status_code):
        mock_response = mock.Mock()
        mock_response.status_code = status_code
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def project_submission_data(self, **extra_fields):
        data = {
            "github_link": "https://github.com/test/project",
            "commit_id": "1234567",
        }
        data.update(extra_fields)
        return data

    def project_confirmation_data(self):
        return self.project_submission_data(
            **{
                "learning_in_public_links[]": [
                    "https://example.com/project-notes"
                ],
            },
            time_spent="2",
            problems_comments="No blockers.",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )

    def project_delete_submission_data(self):
        return self.project_submission_data(
            github_link="https://github.com/existing/repo",
            commit_id="123456e",
            time_spent="3",
            problems_comments="No issues encountered.",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/issues/266"
            ),
            action="delete",
        )

    def closed_project_submission_data(self):
        return self.project_submission_data(
            github_link="https://github.com/existing/repo",
            commit_id="1234567",
            time_spent="2",
            problems_comments="Encountered an issue with...",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )

    def close_project_submissions(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

    def post_project(self, data, execute_callbacks=False):
        self.client.login(**credentials)
        if not execute_callbacks:
            return self.client.post(self.project_url(), data)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                self.project_url(), data, HTTP_HOST="localhost"
            )

    def get_project_submission(self):
        return ProjectSubmission.objects.get(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )

    def project_submission_count(self):
        return ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        ).count()

    def create_existing_project_submission(self, **extra_fields):
        data = {
            "github_link": "https://github.com/existing/repo",
            "commit_id": "123456a",
        }
        data.update(extra_fields)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            **data,
        )

    def assert_project_submission_matches(self, submission, data):
        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        if "time_spent" in data:
            self.assertEqual(submission.time_spent, int(data["time_spent"]))
        if "problems_comments" in data:
            self.assertEqual(
                submission.problems_comments,
                data["problems_comments"],
            )
        if "faq_contribution_url" in data:
            self.assertEqual(
                submission.faq_contribution_url,
                data["faq_contribution_url"],
            )

    def assert_submission_form_values(self, submission, data, links):
        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        self.assertEqual(submission.learning_in_public_links, links)

    def assert_db_submission_unchanged(self, submission, data, links):
        submission.refresh_from_db()
        self.assertNotEqual(submission.github_link, data["github_link"])
        self.assertNotEqual(submission.commit_id, data["commit_id"])
        self.assertNotEqual(submission.learning_in_public_links, links)

    def assert_project_confirmation_payload(self, payload, submission):
        self.assertEqual(payload["email"], "test@test.com")
        self.assertEqual(
            payload["template_key"],
            "project-submission-confirmation",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertEqual(
            payload["idempotency_key"],
            (
                f"project-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "project_submission",
        )

    def assert_project_confirmation_context(self, payload, submission):
        context = payload["context"]
        self.assertEqual(context["submission_id"], submission.id)
        self.assertEqual(context["course_slug"], "test-course")
        self.assertEqual(context["project_slug"], "test-project")
        self.assertEqual(
            context["update_url"],
            "http://localhost/test-course/project/test-project",
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
            (
                "Your project submission for Test Project in "
                "Test Course was saved."
            ),
        )

    def assert_project_submission_fields(self, payload):
        self.assertEqual(
            payload["context"]["submission_fields"],
            [
                {
                    "key": "github_link",
                    "label": "GitHub repository",
                    "value": "https://github.com/test/project",
                },
                {
                    "key": "commit_id",
                    "label": "Commit ID",
                    "value": "1234567",
                },
                {
                    "key": "learning_in_public_links",
                    "label": "Learning in public links",
                    "value": "https://example.com/project-notes",
                    "values": ["https://example.com/project-notes"],
                },
                {
                    "key": "time_spent",
                    "label": "Time spent on project",
                    "value": "2 hours",
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
                        "https://github.com/DataTalksClub/faq/pull/266"
                    ),
                },
            ],
        )

    def test_project_detail_unauthenticated_no_submission(self):
        """
        Test the project details view for unauthenticated users with no submissions.
        """
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context
        submission = context["submission"]

        self.assertIsNone(submission)

        self.assertFalse(context["is_authenticated"])
        self.assertFalse(context["disabled"])
        self.assertTrue(context["accepting_submissions"])

        self.assertEqual(context["project"], self.project)
        self.assertEqual(context["course"], self.course)

    def test_project_detail_displays_optional_instructions_url(self):
        self.project.instructions_url = (
            "https://example.com/project-instructions"
        )
        self.project.save()

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instructions")
        self.assertContains(response, self.project.instructions_url)
        self.assertContains(response, "fas fa-external-link-alt")

    def test_project_detail_hides_missing_instructions_url(self):
        self.project.instructions_url = ""
        self.project.save()

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Instructions")

    # def test_project_detail_authenticated_with_submission(self):
    #     self.client.login(
    #         username=credentials["username"],
    #         password=credentials["password"],
    #     )
    #     url = reverse(
    #         "project", args=[self.course.slug, self.project.slug]
    #     )
    #     response = self.client.get(url)
    #     self.assertEqual(response.status_code, 200)
    #     self.assertIn("submission", response.context)

    #     context = response.context
    #     submission = context["submission"]

    #     self.assertIsNotNone(submission)
    # More assertions here for the submission details...

    def test_project_detail_authenticated_certificate_name_is_used(
        self,
    ):
        self.enrollment.display_name = "Display Name"
        self.enrollment.save()
        self.user.certificate_name = "Certificate Name"
        self.user.save()

        self.client.login(
            username=credentials["username"],
            password=credentials["password"],
        )
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context
        ceritificate_name = context["ceritificate_name"]

        self.assertEqual(ceritificate_name, "Certificate Name")

    def test_project_detail_authenticated_without_submission(self):
        self.project.learning_in_public_cap_project = 7
        self.project.faq_contribution_field = True
        self.project.save()

        self.client.login(
            username=credentials["username"],
            password=credentials["password"],
        )
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        submission = context["submission"]
        self.assertIsNone(submission)

        self.assertTrue(context["is_authenticated"])
        self.assertContains(response, "Status: Not saved yet")
        self.assertContains(response, "Save submission")
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/course-management-platform/learning-in-public/",
        )
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/faq/",
        )
        self.assertContains(
            response,
            (
                "You can save your project now and keep working on it. "
                "Update the commit ID before the deadline when you have "
                "a newer version."
            ),
        )

    def test_project_detail_authenticated_with_submission_copy(self):
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/project",
            commit_id="abc1234",
        )

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Last saved at:")
        self.assertContains(response, "Update submission")
        self.assertContains(
            response,
            (
                "You can save your project now and keep working on it. "
                "Update the commit ID before the deadline when you have "
                "a newer version."
            ),
        )

    def test_project_detail_when_peer_reviewing(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertEqual(context["project"], self.project)
        self.assertTrue(context["disabled"])

    def test_project_detail_with_scored_project(self):
        """
        Test the project details view with a project that has been scored.
        """
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context)
        # Check if the context has 'disabled' as True
        self.assertTrue(response.context["disabled"])
        self.assertContains(
            response,
            "submission window is closed",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Submission details",
            status_code=200,
        )

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_no_submissions(
        self, mock_get, mock_head
    ):
        """
        Test posting a project submission when there are no existing submissions.
        """
        self.mock_url_check_status(mock_get, mock_head, 200)
        data = self.project_confirmation_data()
        data["github_link"] = "https://httpbin.org/status/200"
        data["problems_comments"] = "Encountered an issue with..."

        response = self.post_project(data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project_submission_count(), 1)
        self.assert_project_submission_matches(
            self.get_project_submission(),
            data,
        )

    @override_settings(PUBLIC_BASE_URL="")
    @mock.patch("courses.views.project.send_transactional_email")
    @mock.patch(
        "courses.views.project.sync_project_submission_to_datamailer"
    )
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_sends_confirmation_email(
        self, mock_get, mock_head, sync_submission, send_email
    ):
        self.mock_url_check_status(mock_get, mock_head, 200)

        response = self.post_project(
            self.project_confirmation_data(),
            execute_callbacks=True,
        )
        self.assertEqual(response.status_code, 302)

        submission = self.get_project_submission()
        sync_submission.assert_called_once_with(submission)
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]

        self.assert_project_confirmation_payload(payload, submission)
        self.assert_project_confirmation_context(payload, submission)
        self.assert_project_submission_fields(payload)
        self.assertIn(
            "GitHub repository: https://github.com/test/project",
            payload["context"]["submission_summary_text"],
        )

    @mock.patch("courses.views.project.send_transactional_email")
    @mock.patch(
        "courses.views.project.sync_project_submission_to_datamailer"
    )
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_uses_datamailer_without_local_preference(
        self, mock_get, mock_head, sync_submission, send_email
    ):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    "github_link": "https://github.com/test/project",
                    "commit_id": "1234567",
                },
                HTTP_HOST="localhost",
            )

        self.assertEqual(response.status_code, 302)
        submission = ProjectSubmission.objects.get(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )
        sync_submission.assert_called_once_with(submission)
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]
        self.assertEqual(payload["email"], "test@test.com")
        self.assertEqual(payload["category_tag"], "submission-results")

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_creates_enrollment(
        self, mock_get, mock_head
    ):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

        self.enrollment.delete()

        enrollments = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        )

        self.assertEqual(enrollments.count(), 0)

        self.client.login(**credentials)

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://github.com/existing/repo",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution_url": "https://github.com/DataTalksClub/faq/pull/266",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(enrollments.count(), 1)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_with_submissions(
        self, mock_get, mock_head
    ):
        """
        Test posting a project submission when there are existing submissions.
        """
        self.mock_url_check_status(mock_get, mock_head, 200)
        submission = self.create_existing_project_submission()

        data = self.project_submission_data(
            github_link="https://github.com/existing/repo",
            commit_id="123456e",
            time_spent="3",
            problems_comments="No issues encountered.",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/issues/266"
            ),
        )

        response = self.post_project(data)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.project_submission_count(), 1)
        submission = fetch_fresh(submission)
        self.assert_project_submission_matches(submission, data)

    def test_remove_project_submission(self):
        self.create_existing_project_submission()
        self.assertEqual(self.project_submission_count(), 1)

        response = self.post_project(self.project_delete_submission_data())
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.project_submission_count(), 0)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_with_certificate_name(
        self, mock_get, mock_head
    ):
        """
        Test that submitting a project with certificate name saves it to the user.
        """
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

        self.client.login(**credentials)

        self.user.certificate_name = None
        self.user.save()

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://github.com/test/repo",
            "commit_id": "abcd123",
            "certificate_name": "John Doe",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()

        self.assertEqual(self.user.certificate_name, "John Doe")

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_existing_submission_post_with_invalid_link_preserves_form_values(
        self, mock_get, mock_head
    ):
        self.mock_url_check_status(mock_get, mock_head, 404)

        self.project.learning_in_public_cap_project = 7
        self.project.save()

        db_submission = self.create_existing_project_submission(
            github_link="https://github.com/alexeygrigorev/llm-rag-workshop",
            learning_in_public_links=[
                "https://example.com/post-1",
                "https://example.com/post-2",
            ],
        )

        learning_in_public_links = [
            "https://example.com/post-1",
            "https://example.com/post-2",
            "https://example.com/post-3",
        ]
        data = self.project_submission_data(
            github_link="https://github.com/alexeygrigorev/404",
            commit_id="123456f",
            **{"learning_in_public_links[]": learning_in_public_links},
        )

        response = self.post_project(data)

        self.assertEqual(response.status_code, 200)
        submission = response.context["submission"]
        self.assert_submission_form_values(
            submission, data, learning_in_public_links
        )
        self.assert_db_submission_unchanged(
            db_submission, data, learning_in_public_links
        )

    def test_project_submission_not_accepting_responses(self):
        """
        Test posting a project submission when there are no existing submissions.
        """
        self.close_project_submissions()

        response = self.post_project(self.closed_project_submission_data())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Project submission form is closed.",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Submission details",
            status_code=200,
        )

        self.assertEqual(self.project_submission_count(), 0)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_invalid_link_no_submission(
        self, mock_get, mock_head
    ):
        """
        When the link is invalid and there's no submission yet,
        no submission is created
        """
        self.mock_url_check_status(mock_get, mock_head, 404)
        data = self.project_submission_data(
            github_link="https://github.com/alexeygrigorev/404",
        )

        response = self.post_project(data)

        self.assertEqual(response.status_code, 200)
        self.assert_project_submission_matches(
            response.context["submission"],
            data,
        )
        self.assertEqual(self.project_submission_count(), 0)
