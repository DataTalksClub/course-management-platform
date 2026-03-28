import json

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Course, Project
from courses.models.project import ProjectState


class ProjectsAPITestCase(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def _create_project(self, slug="proj1", state=ProjectState.CLOSED.value):
        return Project.objects.create(
            course=self.course,
            title="Project 1",
            slug=slug,
            description="Description",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=state,
        )

    def test_list_projects(self):
        self._create_project()
        response = self.client.get(f"/api/courses/{self.course.slug}/projects/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 1)

    def test_create_project(self):
        payload = {
            "name": "Project 2",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
        }
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["created"][0]["state"], "CL")

    def test_create_project_bulk(self):
        payload = [
            {
                "name": "P1",
                "submission_due_date": "2026-04-01T23:59:59Z",
                "peer_review_due_date": "2026-04-08T23:59:59Z",
            },
            {
                "name": "P2",
                "submission_due_date": "2026-05-01T23:59:59Z",
                "peer_review_due_date": "2026-05-08T23:59:59Z",
            },
        ]
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 2)

    def test_create_project_missing_fields(self):
        payload = {"name": "No dates"}
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_project_state(self):
        proj = self._create_project()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/",
            json.dumps({"state": "CS"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        proj.refresh_from_db()
        self.assertEqual(proj.state, "CS")

    def test_patch_project_invalid_state(self):
        proj = self._create_project()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/",
            json.dumps({"state": "XX"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_project_closed(self):
        proj = self._create_project(state=ProjectState.CLOSED.value)
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(id=proj.id).exists())

    def test_delete_project_not_closed(self):
        proj = self._create_project(state=ProjectState.COLLECTING_SUBMISSIONS.value)
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Project.objects.filter(id=proj.id).exists())
