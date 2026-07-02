"""
Tests for project-related data API views.

Tests for project_data_view endpoint.
"""

from .project_base import ProjectDataAPITestBase


class ProjectDataAPITestCase(ProjectDataAPITestBase):
    """Tests for project_data_view endpoint."""

    def test_project_data_view(self):
        project = self.create_project()
        submission = self.create_project_submission(project)

        export_url = self.project_export_url(project)
        response = self.client.get(export_url)

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()
        self.assert_course_data(actual_result)
        self.assert_project_data(actual_result, project)
        self.assert_submission_data(actual_result, submission)
