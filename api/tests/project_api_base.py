import json

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
)
from courses.models.project import ProjectState


PROJECT_INSTRUCTIONS_URL = (
    "https://github.com/DataTalksClub/test/blob/main/project.md"
)


class ProjectAPITestBase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def _create_project(
        self, slug="proj1", state=ProjectState.CLOSED.value
    ):
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        return Project.objects.create(
            course=self.course,
            title="Project 1",
            slug=slug,
            description="Description",
            instructions_url=PROJECT_INSTRUCTIONS_URL,
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=state,
        )

    def _create_project_submission(self, project, username):
        user = CustomUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            password="password",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        return ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link=f"https://github.com/{username}/project",
            commit_id="abc123",
        )

    def _non_staff_client(self, username):
        non_staff = CustomUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def _non_staff_project_mutation_responses(self, client, project):
        create_response = self._non_staff_project_create_response(client)
        patch_response = self._non_staff_project_patch_response(
            client, project
        )
        put_response = self._non_staff_project_put_response(client)
        delete_response = self._non_staff_project_delete_response(
            client, project
        )
        return create_response, patch_response, put_response, delete_response

    def _non_staff_project_create_response(self, client):
        payload = {
            "name": "Created by nonstaff",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
        }
        body = json.dumps(payload)
        return client.post(
            f"/api/courses/{self.course.slug}/projects/",
            body,
            content_type="application/json",
        )

    def _non_staff_project_patch_response(self, client, project):
        payload = {"description": "Changed by nonstaff"}
        body = json.dumps(payload)
        return client.patch(
            f"/api/courses/{self.course.slug}/projects/{project.id}/",
            body,
            content_type="application/json",
        )

    def _non_staff_project_put_response(self, client):
        payload = {
            "name": "Put by nonstaff",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
        }
        body = json.dumps(payload)
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "nonstaff-put/"
        )
        return client.put(
            url,
            body,
            content_type="application/json",
        )

    def _non_staff_project_delete_response(self, client, project):
        return client.delete(
            f"/api/courses/{self.course.slug}/projects/{project.id}/"
        )
