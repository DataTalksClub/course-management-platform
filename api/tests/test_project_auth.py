from api.tests.project_api_base import ProjectAPITestBase
from courses.models import Project


class ProjectAuthAPITestCase(ProjectAPITestBase):
    def test_project_mutations_require_staff_token(self):
        project = self._create_project(slug="staff-only-project")
        client = self._non_staff_client("project-mutation-nonstaff")
        responses = self._non_staff_project_mutation_responses(
            client, project
        )

        for response in responses:
            self._assert_staff_token_required(response)

        nonstaff_project_exists = Project.objects.filter(
            course=self.course,
            slug="nonstaff-put",
        ).exists()
        self.assertFalse(nonstaff_project_exists)
        project.refresh_from_db()
        self.assertEqual(project.description, "Description")
        original_project_exists = Project.objects.filter(
            id=project.id
        ).exists()
        self.assertTrue(original_project_exists)
