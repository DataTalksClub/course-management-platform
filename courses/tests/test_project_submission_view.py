from unittest import mock

from courses.models import Enrollment
from courses.tests.project_submission_view_base import (
    ProjectSubmissionViewTestBase,
)
from courses.tests.project_view_base import fetch_fresh


class ProjectSubmissionCreateViewTestCase(ProjectSubmissionViewTestBase):
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
        submission_count = self.project_submission_count()
        self.assertEqual(submission_count, 1)
        submission = self.get_project_submission()
        self.assert_project_submission_matches(
            submission,
            data,
        )

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
        initial_enrollment_count = enrollments.count()
        self.assertEqual(initial_enrollment_count, 0)

        data = {
            "github_link": "https://github.com/existing/repo",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution_url": "https://github.com/DataTalksClub/faq/pull/266",
        }
        response = self.post_project(data)

        self.assertEqual(response.status_code, 302)
        final_enrollment_count = enrollments.count()
        self.assertEqual(final_enrollment_count, 1)


class ProjectSubmissionUpdateViewTestCase(ProjectSubmissionViewTestBase):
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

        submission_count = self.project_submission_count()
        self.assertEqual(submission_count, 1)
        submission = fetch_fresh(submission)
        self.assert_project_submission_matches(submission, data)

    def test_remove_project_submission(self):
        self.create_existing_project_submission()
        initial_submission_count = self.project_submission_count()
        self.assertEqual(initial_submission_count, 1)

        data = self.project_delete_submission_data()
        response = self.post_project(data)

        self.assertEqual(response.status_code, 302)
        final_submission_count = self.project_submission_count()
        self.assertEqual(final_submission_count, 0)


class ProjectSubmissionCertificateNameTestCase(
    ProjectSubmissionViewTestBase
):
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
