import json

from courses.models import (
    Project,
    ProjectSubmission,
)
from courses.models.project import ProjectState
from api.tests.project_api_base import (
    PROJECT_INSTRUCTIONS_URL,
    ProjectAPITestBase,
)


class ProjectsAPITestCase(ProjectAPITestBase):
    def test_list_projects(self):
        self._create_project()
        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["submissions_count"], 0)
        self.assertTrue(data["projects"][0]["can_delete"])

    def test_create_project(self):
        payload = {
            "name": "Project 2",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "instructions_url": PROJECT_INSTRUCTIONS_URL,
        }
        url = f"/api/courses/{self.course.slug}/projects/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(
            data["created"][0]["instructions_url"],
            PROJECT_INSTRUCTIONS_URL,
        )
        self.assertEqual(data["created"][0]["state"], "CL")

    def test_create_project_without_instructions_url(self):
        payload = {
            "name": "Project without instructions",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
        }
        url = f"/api/courses/{self.course.slug}/projects/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(
            data["created"][0]["title"],
            "Project without instructions",
        )
        self.assertIsNone(data["created"][0]["instructions_url"])

    def test_create_project_bulk(self):
        payload = [
            {
                "name": "P1",
                "submission_due_date": "2026-04-01T23:59:59Z",
                "peer_review_due_date": "2026-04-08T23:59:59Z",
                "instructions_url": PROJECT_INSTRUCTIONS_URL,
            },
            {
                "name": "P2",
                "submission_due_date": "2026-05-01T23:59:59Z",
                "peer_review_due_date": "2026-05-08T23:59:59Z",
                "instructions_url": PROJECT_INSTRUCTIONS_URL,
            },
        ]
        url = f"/api/courses/{self.course.slug}/projects/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 2)

    def test_create_project_missing_fields(self):
        payload = {"name": "No dates"}
        url = f"/api/courses/{self.course.slug}/projects/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_project_state(self):
        proj = self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        patch_payload = {"state": "CS"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        proj.refresh_from_db()
        self.assertEqual(proj.state, "CS")

    def test_get_project_detail(self):
        proj = self._create_project()

        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], proj.id)
        self.assertEqual(data["slug"], "proj1")
        self.assertTrue(data["can_delete"])

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

    def test_patch_project_invalid_state(self):
        proj = self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        patch_payload = {"state": "XX"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_project_closed(self):
        proj = self._create_project(state=ProjectState.CLOSED.value)
        url = f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        project_exists = Project.objects.filter(id=proj.id).exists()
        self.assertFalse(project_exists)

    def test_delete_project_not_closed(self):
        proj = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        url = f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_not_closed")
        project_exists = Project.objects.filter(id=proj.id).exists()
        self.assertTrue(project_exists)

    def test_delete_project_with_submissions_is_blocked(self):
        proj = self._create_project(state=ProjectState.CLOSED.value)
        submission = self._create_project_submission(
            proj,
            "project-delete-submitter",
        )

        url = f"/api/courses/{self.course.slug}/projects/{proj.id}/"
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
        project_exists = Project.objects.filter(id=proj.id).exists()
        submission_exists = ProjectSubmission.objects.filter(
            id=submission.id
        ).exists()
        self.assertTrue(project_exists)
        self.assertTrue(submission_exists)

    def test_delete_project_by_slug_closed_without_submissions(self):
        proj = self._create_project(slug="draft-project")

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/by-slug/draft-project/"
        )

        self.assertEqual(response.status_code, 200)
        project_exists = Project.objects.filter(id=proj.id).exists()
        self.assertFalse(project_exists)
