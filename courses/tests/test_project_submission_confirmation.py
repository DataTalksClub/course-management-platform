from unittest import mock

from django.test import override_settings

from courses.tests.project_submission_view_base import (
    ProjectSubmissionViewTestBase,
)


class ProjectSubmissionConfirmationTestCase(ProjectSubmissionViewTestBase):
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
            response = self.post_project_confirmation_with_email(
                mock_get,
                mock_head,
            )

        self.assert_project_confirmation_email(
            response,
            sync_submission,
            send_email,
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
