import json

from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import CustomUser
from courses.models import Answer, Enrollment, Submission
from api.tests.homework_api_base import (
    HOMEWORK_INSTRUCTIONS_URL,
    HomeworkAPITestBase,
)


class HomeworksAPITestCase(HomeworkAPITestBase):
    def _seed_homework_with_counts(self, slug):
        homework = self._create_homework(slug=slug)
        question = self._create_scored_question(homework)
        student = CustomUser.objects.create(
            username=f"student-{slug}",
            email=f"student-{slug}@example.com",
            password="x",
        )
        enrollment = Enrollment.objects.create(
            student=student, course=self.course
        )
        submission = Submission.objects.create(
            homework=homework, student=student, enrollment=enrollment
        )
        Answer.objects.create(
            submission=submission, question=question, answer_text="4"
        )

    def _list_query_count(self):
        url = f"/api/courses/{self.course.slug}/homeworks/"
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_list_homeworks_query_count_is_constant(self):
        """The list endpoint must not run counts per homework row."""
        self._seed_homework_with_counts("hw1")
        self._seed_homework_with_counts("hw2")
        baseline = self._list_query_count()

        for index in range(3, 9):
            self._seed_homework_with_counts(f"hw{index}")
        grown = self._list_query_count()

        self.assertEqual(baseline, grown)

    def test_list_homeworks(self):
        self._create_homework()
        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        homeworks_count = len(data["homeworks"])
        self.assertEqual(homeworks_count, 1)
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
        created_count = len(data["created"])
        self.assertEqual(created_count, 1)
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
        created_count = len(data["created"])
        self.assertEqual(created_count, 2)

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
