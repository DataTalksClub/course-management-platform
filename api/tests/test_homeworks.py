import json

from api.tests.homework_api_base import (
    HOMEWORK_INSTRUCTIONS_URL,
    HomeworkAPITestBase,
)


class HomeworksAPITestCase(HomeworkAPITestBase):
    def test_list_homeworks(self):
        self._create_homework()
        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["homeworks"]), 1)
        self.assertEqual(data["homeworks"][0]["slug"], "hw1")
        self.assertEqual(data["homeworks"][0]["submissions_count"], 0)
        self.assertTrue(data["homeworks"][0]["can_delete"])

    def test_create_homework(self):
        payload = {
            "name": "Homework 2",
            "due_date": "2026-04-01T23:59:59Z",
            "description": "New homework",
        }
        url = f"/api/courses/{self.course.slug}/homeworks/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["created"][0]["title"], "Homework 2")
        self.assertIsNone(data["created"][0]["instructions_url"])
        self.assertEqual(data["created"][0]["state"], "CL")

    def test_create_homework_with_instructions_url(self):
        payload = {
            "name": "Homework with instructions",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
        }
        url = f"/api/courses/{self.course.slug}/homeworks/"
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
            "Homework with instructions",
        )
        self.assertEqual(
            data["created"][0]["instructions_url"],
            HOMEWORK_INSTRUCTIONS_URL,
        )

    def test_create_homework_bulk(self):
        payload = [
            {
                "name": "HW A",
                "due_date": "2026-04-01T23:59:59Z",
                "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            },
            {
                "name": "HW B",
                "due_date": "2026-04-02T23:59:59Z",
                "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            },
        ]
        url = f"/api/courses/{self.course.slug}/homeworks/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 2)

    def test_create_homework_with_questions(self):
        payload = {
            "name": "HW with Q",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            "questions": [
                {
                    "text": "What is 2+2?",
                    "question_type": "MC",
                    "possible_answers": ["3", "4", "5"],
                    "correct_answer": "2",
                }
            ],
        }
        url = f"/api/courses/{self.course.slug}/homeworks/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"][0]["questions_count"], 1)

    def test_create_homework_missing_fields(self):
        payload = {"name": "No date"}
        url = f"/api/courses/{self.course.slug}/homeworks/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_homework_duplicate_slug(self):
        self._create_homework(slug="hw1")
        payload = {
            "name": "HW 1",
            "slug": "hw1",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
        }
        url = f"/api/courses/{self.course.slug}/homeworks/"
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
