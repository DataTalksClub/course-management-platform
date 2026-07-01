from datetime import timedelta

from django.utils import timezone

from api.tests.project_api_base import ProjectAPITestBase
from courses.models.project import ProjectState


class ProjectActionsAPITestCase(ProjectAPITestBase):
    def test_assign_project_peer_reviews(self):
        project = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        project.submission_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.number_of_peers_to_evaluate = 2
        project.save()
        for index in range(4):
            self._create_project_submission(project, f"student-{index}")

        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/assign-reviews/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["project_slug"], "proj1")
        self.assertEqual(
            data["state"], ProjectState.PEER_REVIEWING.value
        )
        self.assertEqual(data["assigned_peer_reviews_count"], 8)
        self.assertEqual(data["peer_reviews_count"], 8)

    def test_assign_project_peer_reviews_by_slug_blocked_when_closed(
        self,
    ):
        project = self._create_project(
            slug="closed-project",
            state=ProjectState.CLOSED.value,
        )
        project.submission_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.save()

        response = self.client.post(
            (
                f"/api/courses/{self.course.slug}/projects/by-slug/"
                "closed-project/assign-reviews/"
            )
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["project_slug"], "closed-project")
        self.assertEqual(data["state"], ProjectState.CLOSED.value)
        self.assertEqual(data["assigned_peer_reviews_count"], 0)

    def test_project_actions_require_staff_token(self):
        project = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        client = self._non_staff_client("project-nonstaff")

        response = client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/assign-reviews/"
        )

        self._assert_staff_token_required(response)
