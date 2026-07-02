import json

from courses.models import Project
from api.tests.project_api_base import (
    PROJECT_INSTRUCTIONS_URL,
    ProjectAPITestBase,
)


class ProjectPatchAPITestCase(ProjectAPITestBase):
    def test_patch_project_state(self):
        project = self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"
        patch_payload = {"state": "CS"}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.state, "CS")

    def test_patch_project_by_slug(self):
        self._create_project(slug="project-by-slug")
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "project-by-slug/"
        )
        patch_payload = {"description": "Updated by slug"}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Updated by slug")
        self.assertEqual(data["slug"], "project-by-slug")


class ProjectPutSuccessAPITestCase(ProjectAPITestBase):
    def test_put_project_by_slug_creates_project(self):
        payload = {
            "name": "Project From Put",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "description": "Created idempotently",
            "instructions_url": PROJECT_INSTRUCTIONS_URL,
        }
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "project-put/"
        )
        request_body = json.dumps(payload)

        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "project-put")
        self.assertEqual(data["title"], "Project From Put")

    def test_put_project_by_slug_updates_project(self):
        project = self._create_project(slug="project-put")
        payload = {
            "title": "Updated Project",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "description": "Updated idempotently",
        }
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "project-put/"
        )
        request_body = json.dumps(payload)

        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.title, "Updated Project")
        self.assertEqual(project.description, "Updated idempotently")


class ProjectPutValidationAPITestCase(ProjectAPITestBase):
    def test_put_project_by_slug_missing_create_fields(self):
        payload = {"title": "Missing dates"}
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "project-put/"
        )
        request_body = json.dumps(payload)

        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "missing_required_fields"
        )

    def test_put_project_invalid_state_does_not_create(self):
        payload = {
            "name": "Bad State",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "instructions_url": PROJECT_INSTRUCTIONS_URL,
            "state": "XX",
        }
        url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            "project-put/"
        )
        request_body = json.dumps(payload)

        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "invalid_project_state"
        )
        project_exists = Project.objects.filter(
            course=self.course,
            slug="project-put",
        ).exists()
        self.assertFalse(project_exists)


class ProjectPatchValidationAPITestCase(ProjectAPITestBase):
    def test_patch_project_invalid_state(self):
        project = self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"
        patch_payload = {"state": "XX"}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
