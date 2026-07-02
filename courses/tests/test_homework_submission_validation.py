from unittest import mock

from courses.tests.homework_submission_validation_base import (
    HomeworkSubmissionValidationBase,
)


class HomeworkSubmissionValidationTests(HomeworkSubmissionValidationBase):
    def assert_invalid_homework_url_response(self, response, homework_url):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The submitted GitHub link")
        self.assertContains(response, "does not exist")
        self.assertContains(response, f'value="{homework_url}"')
        self.assertContains(
            response,
            'class="form-control mt-2 is-invalid"',
        )
        self.assertContains(
            response,
            "Check that the repository exists and is public.",
        )
        self.assertContains(
            response,
            f'id="radio-{self.question1.id}-1"',
        )
        self.assertContains(response, "checked")
        self.assertContains(
            response,
            'value="Some other text"',
        )
        self.assertContains(
            response,
            'value="3.141516"',
        )
        self.assert_no_submission()

    def test_submit_homework_rejects_non_faq_contribution_url(self):
        self.enable_faq_contribution_field()
        faq_url = (
            "https://gist.github.com/Sanjomwa/"
            "2dcb7a95baa01c07c10048fbac1a8461"
        )
        post_data = self.updated_answer_post_data(
            faq_contribution_url=faq_url,
        )

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "FAQ contribution must be a DataTalksClub/faq issue "
            "or pull request URL",
        )
        self.assertContains(
            response,
            'value="https://gist.github.com/Sanjomwa/'
            '2dcb7a95baa01c07c10048fbac1a8461"',
        )
        self.assertContains(
            response,
            'class="form-control mt-2 is-invalid"',
        )
        self.assert_no_submission()

    def test_submit_homework_accepts_faq_issue_url(self):
        self.enable_faq_contribution_field()
        self.client.login(
            username="test@test.com",
            password="12345",
        )

        faq_url = "https://github.com/DataTalksClub/faq/issues/281"
        post_data = self.updated_answer_post_data(
            faq_contribution_url=faq_url,
        )

        homework_url = self.homework_url()
        response = self.client.post(homework_url, post_data)

        self.assertEqual(response.status_code, 302)
        submission = self.get_saved_submission()
        self.assertEqual(submission.faq_contribution_url, faq_url)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_url_validation_404_error(
        self, mock_get, mock_head
    ):
        self.mock_failed_url_checks(mock_get, mock_head)
        self.enable_homework_url_field()
        homework_url = "https://github.com/nonexistent/repo"
        post_data = self.updated_answer_post_data(homework_url=homework_url)

        response = self.post_homework(post_data)

        self.assert_invalid_homework_url_response(response, homework_url)
