from unittest.mock import patch

from courses.tests.homework_submission_integration_base import (
    HomeworkSubmissionIntegrationBase,
)
from courses.tests.homework_submission_learning_links_helpers import (
    assert_current_homework_not_submitted,
    assert_reused_learning_link_rejected,
    create_previous_homework_submission_with_learning_link,
    reused_learning_link_post_data,
)
from courses.views.homework_learning_links import (
    find_duplicate_learning_in_public_links,
)


class HomeworkSubmissionLearningLinksTest(HomeworkSubmissionIntegrationBase):
    @patch("courses.views.homework_confirmation.send_transactional_email")
    def test_reused_learning_in_public_link_is_rejected(
        self,
        send_email,
    ):
        create_previous_homework_submission_with_learning_link(self)

        post_data = reused_learning_link_post_data()
        url = self.homework_url()
        response = self.client.post(url, post_data)

        assert_reused_learning_link_rejected(self, response)
        assert_current_homework_not_submitted(self)
        send_email.assert_not_called()

    def test_duplicate_learning_in_public_finder_checks_project_submissions(
        self,
    ):
        learning_links = ["https://example.com/project-post"]
        self.create_project_submission(learning_links)

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
