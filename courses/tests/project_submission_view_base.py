from dataclasses import dataclass
from typing import Any

from courses.tests.project_view_base import ProjectViewTestBase


@dataclass(frozen=True)
class InvalidProjectSubmissionExpectation:
    response: Any
    db_submission: Any
    data: dict[str, Any]
    learning_in_public_links: list[str]


class ProjectSubmissionViewTestBase(ProjectViewTestBase):
    def post_project_confirmation_with_email(self, mock_get, mock_head):
        self.mock_url_check_status(mock_get, mock_head, 200)
        data = self.project_confirmation_data()
        return self.post_project(data, execute_callbacks=True)

    def assert_project_confirmation_email(
        self,
        response,
        sync_submission,
        send_email,
    ):
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

    def prepare_project_with_learning_cap(self):
        self.project.learning_in_public_cap_project = 7
        self.project.save()

    def invalid_link_existing_submission(self):
        learning_in_public_links = [
            "https://example.com/post-1",
            "https://example.com/post-2",
        ]
        return self.create_existing_project_submission(
            github_link="https://github.com/alexeygrigorev/llm-rag-workshop",
            learning_in_public_links=learning_in_public_links,
        )

    def invalid_project_submission_links(self):
        links = []
        links.append("https://example.com/post-1")
        links.append("https://example.com/post-2")
        links.append("https://example.com/post-3")
        return links

    def invalid_project_submission_data(self, learning_in_public_links):
        link_fields = {"learning_in_public_links[]": learning_in_public_links}
        return self.project_submission_data(
            github_link="https://github.com/alexeygrigorev/404",
            commit_id="123456f",
            **link_fields,
        )

    def assert_invalid_project_submission_preserved(
        self,
        expectation,
    ):
        self.assertEqual(expectation.response.status_code, 200)
        submission = expectation.response.context["submission"]
        self.assert_submission_form_values(
            submission,
            expectation.data,
            expectation.learning_in_public_links,
        )
        self.assert_db_submission_unchanged(
            expectation.db_submission,
            expectation.data,
            expectation.learning_in_public_links,
        )
