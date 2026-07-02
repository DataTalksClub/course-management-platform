from unittest.mock import patch

from django.test import override_settings

from courses.tests.homework_submission_integration_base import (
    HomeworkSubmissionIntegrationBase,
)
from courses.tests.homework_submission_confirmation_helpers import (
    assert_confirmation_context,
    assert_confirmation_payload_basics,
    assert_confirmation_summary,
    assert_submission_fields,
    assert_submitted_answers,
    confirmation_post_data,
    datamailer_preference_post_data,
    public_base_url_post_data,
)


class HomeworkSubmissionConfirmationTest(HomeworkSubmissionIntegrationBase):
    @override_settings(PUBLIC_BASE_URL="")
    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_homework_submission_sends_confirmation_email(
        self,
        send_email,
    ):
        post_data = confirmation_post_data(self)
        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        submission = self.get_submission()
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]

        assert_confirmation_payload_basics(self, payload, submission)
        assert_confirmation_context(self, payload, submission)
        assert_submission_fields(self, payload)
        assert_submitted_answers(self, payload)
        assert_confirmation_summary(self, payload)

    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_homework_submission_uses_datamailer_without_local_preference(
        self,
        send_email,
    ):
        post_data = datamailer_preference_post_data(self)

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        self.assert_submission_exists()
        send_email.assert_called_once()
        payload = send_email.call_args.args[0]
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["category_tag"], "submission-results")

    @override_settings(PUBLIC_BASE_URL="https://dev.courses.datatalks.club")
    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_homework_confirmation_uses_public_base_url(
        self,
        send_email,
    ):
        post_data = public_base_url_post_data(self)
        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        payload = send_email.call_args.args[0]
        self.assertEqual(
            payload["context"]["update_url"],
            "https://dev.courses.datatalks.club/course/homework/hw1",
        )
