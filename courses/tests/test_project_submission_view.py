from unittest import mock

from django.test import override_settings

from courses.models import Enrollment
from courses.tests.project_view_base import (
    ProjectViewTestBase,
    fetch_fresh,
)


class ProjectSubmissionViewTestCase(ProjectViewTestBase):
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_no_submissions(
        self, mock_get, mock_head
    ):
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
    def test_project_submission_sends_confirmation_email(self):
        with (
            mock.patch("requests.get") as mock_get,
            mock.patch("requests.head") as mock_head,
            mock.patch(
                "courses.views.project_submission_edit."
                "sync_project_submission_to_datamailer"
            ) as sync_submission,
            mock.patch(
                "courses.views.project_confirmation.send_transactional_email"
            ) as send_email,
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

    def test_project_submission_uses_datamailer_without_local_preference(self):
        with (
            mock.patch("requests.get") as mock_get,
            mock.patch("requests.head") as mock_head,
            mock.patch(
                "courses.views.project_submission_edit."
                "sync_project_submission_to_datamailer"
            ) as sync_submission,
            mock.patch(
                "courses.views.project_confirmation.send_transactional_email"
            ) as send_email,
        ):
            self.mock_url_check_status(mock_get, mock_head, 200)

            data = self.project_submission_data()
            response = self.post_project(data, execute_callbacks=True)

        self.assertEqual(response.status_code, 302)
        submission = self.get_project_submission()
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
        self.mock_url_check_status(mock_get, mock_head, 200)
        self.enrollment.delete()
        enrollments = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        )
        self.assertEqual(enrollments.count(), 0)

        data = {
            "github_link": "https://github.com/existing/repo",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution_url": "https://github.com/DataTalksClub/faq/pull/266",
        }
        response = self.post_project(data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(enrollments.count(), 1)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_post_with_submissions(
        self, mock_get, mock_head
    ):
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
        self.mock_url_check_status(mock_get, mock_head, 200)
        self.user.certificate_name = None
        self.user.save()

        data = {
            "github_link": "https://github.com/test/repo",
            "commit_id": "abcd123",
            "certificate_name": "John Doe",
        }
        response = self.post_project(data)

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
