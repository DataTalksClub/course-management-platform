from unittest import mock

from courses.tests.project_submission_view_base import (
    InvalidProjectSubmissionExpectation,
    ProjectSubmissionViewTestBase,
)


class ProjectSubmissionInvalidExistingViewTestCase(
    ProjectSubmissionViewTestBase
):
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_existing_submission_post_with_invalid_link_preserves_form_values(
        self, mock_get, mock_head
    ):
        self.mock_url_check_status(mock_get, mock_head, 404)
        self.prepare_project_with_learning_cap()
        db_submission = self.invalid_link_existing_submission()
        learning_in_public_links = self.invalid_project_submission_links()
        data = self.invalid_project_submission_data(learning_in_public_links)

        response = self.post_project(data)

        expectation = InvalidProjectSubmissionExpectation(
            response=response,
            db_submission=db_submission,
            data=data,
            learning_in_public_links=learning_in_public_links,
        )
        self.assert_invalid_project_submission_preserved(expectation)


class ProjectSubmissionFaqUrlViewTestCase(ProjectSubmissionViewTestBase):
    """The project FAQ field must enforce the same DataTalksClub/faq URL rule
    as the homework FAQ field."""

    def enable_faq_contribution_field(self):
        self.project.faq_contribution_field = True
        self.project.save()

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_rejects_non_faq_contribution_url(
        self, mock_get, mock_head
    ):
        self.mock_url_check_status(mock_get, mock_head, 200)
        self.enable_faq_contribution_field()
        faq_url = (
            "https://gist.github.com/Sanjomwa/"
            "2dcb7a95baa01c07c10048fbac1a8461"
        )
        data = self.project_submission_data(faq_contribution_url=faq_url)

        response = self.post_project(data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "FAQ contribution must be a DataTalksClub/faq issue "
            "or pull request URL",
        )
        self.assertEqual(self.project_submission_count(), 0)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_project_submission_accepts_faq_issue_url(
        self, mock_get, mock_head
    ):
        self.mock_url_check_status(mock_get, mock_head, 200)
        self.enable_faq_contribution_field()
        faq_url = "https://github.com/DataTalksClub/faq/issues/281"
        data = self.project_submission_data(faq_contribution_url=faq_url)

        self.post_project(data)

        submission = self.get_project_submission()
        self.assertEqual(submission.faq_contribution_url, faq_url)


class ProjectSubmissionClosedViewTestCase(ProjectSubmissionViewTestBase):
    def test_project_submission_not_accepting_responses(self):
        self.close_project_submissions()

        data = self.closed_project_submission_data()
        response = self.post_project(data)

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
        submission_count = self.project_submission_count()
        self.assertEqual(submission_count, 0)


class ProjectSubmissionInvalidNewViewTestCase(ProjectSubmissionViewTestBase):
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
        submission_count = self.project_submission_count()
        self.assertEqual(submission_count, 0)
