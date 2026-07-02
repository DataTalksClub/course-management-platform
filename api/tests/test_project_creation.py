import json

from api.tests.project_api_base import (
    PROJECT_INSTRUCTIONS_URL,
    ProjectAPITestBase,
)


class ProjectCreationAPITestCase(ProjectAPITestBase):
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


class ProjectBulkCreationAPITestCase(ProjectAPITestBase):
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
