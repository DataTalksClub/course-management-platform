from courses.models import (
    Project,
    ProjectSubmission,
)
from courses.models.project import ProjectState
from api.tests.project_api_base import ProjectAPITestBase


class ProjectDeletionStateAPITestCase(ProjectAPITestBase):
    def test_delete_project_closed(self):
        project = self._create_project(state=ProjectState.CLOSED.value)
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        project_exists = Project.objects.filter(id=project.id).exists()
        self.assertFalse(project_exists)

    def test_delete_project_not_closed(self):
        project = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_not_closed")
        project_exists = Project.objects.filter(id=project.id).exists()
        self.assertTrue(project_exists)


class ProjectDeletionBlockedAPITestCase(ProjectAPITestBase):
    def test_delete_project_with_submissions_is_blocked(self):
        project = self._create_project(state=ProjectState.CLOSED.value)
        submission = self._create_project_submission(
            project,
            "project-delete-submitter",
        )
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete project with existing submissions",
        )
        self.assertEqual(
            response.json()["code"], "project_has_submissions"
        )
        self.assertEqual(
            response.json()["details"]["submissions_count"],
            1,
        )
        project_exists = Project.objects.filter(id=project.id).exists()
        submission_exists = ProjectSubmission.objects.filter(
            id=submission.id
        ).exists()
        self.assertTrue(project_exists)
        self.assertTrue(submission_exists)


class ProjectDeletionBySlugAPITestCase(ProjectAPITestBase):
    def test_delete_project_by_slug_closed_without_submissions(self):
        project = self._create_project(slug="draft-project")
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "draft-project/"
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        project_exists = Project.objects.filter(id=project.id).exists()
        self.assertFalse(project_exists)
