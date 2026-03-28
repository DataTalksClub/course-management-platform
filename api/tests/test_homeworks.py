import json

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Course, Homework, Question
from courses.models.homework import HomeworkState


class HomeworksAPITestCase(TestCase):

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

    def _create_homework(self, slug="hw1", state=HomeworkState.CLOSED.value):
        return Homework.objects.create(
            course=self.course,
            title="Homework 1",
            slug=slug,
            description="Description",
            due_date=timezone.now(),
            state=state,
        )

    def test_list_homeworks(self):
        self._create_homework()
        response = self.client.get(f"/api/courses/{self.course.slug}/homeworks/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["homeworks"]), 1)
        self.assertEqual(data["homeworks"][0]["slug"], "hw1")

    def test_create_homework(self):
        payload = {
            "name": "Homework 2",
            "due_date": "2026-04-01T23:59:59Z",
            "description": "New homework",
        }
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["created"][0]["title"], "Homework 2")
        self.assertEqual(data["created"][0]["state"], "CL")

    def test_create_homework_bulk(self):
        payload = [
            {"name": "HW A", "due_date": "2026-04-01T23:59:59Z"},
            {"name": "HW B", "due_date": "2026-04-02T23:59:59Z"},
        ]
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 2)

    def test_create_homework_with_questions(self):
        payload = {
            "name": "HW with Q",
            "due_date": "2026-04-01T23:59:59Z",
            "questions": [
                {
                    "text": "What is 2+2?",
                    "question_type": "MC",
                    "possible_answers": ["3", "4", "5"],
                    "correct_answer": "2",
                }
            ],
        }
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"][0]["questions_count"], 1)

    def test_create_homework_missing_fields(self):
        payload = {"name": "No date"}
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_homework_duplicate_slug(self):
        self._create_homework(slug="hw1")
        payload = {"name": "HW 1", "slug": "hw1", "due_date": "2026-04-01T23:59:59Z"}
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_homework_state(self):
        hw = self._create_homework()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/",
            json.dumps({"state": "OP"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "OP")
        hw.refresh_from_db()
        self.assertEqual(hw.state, "OP")

    def test_patch_homework_description(self):
        hw = self._create_homework()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/",
            json.dumps({"description": "Updated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        hw.refresh_from_db()
        self.assertEqual(hw.description, "Updated")

    def test_patch_homework_invalid_state(self):
        hw = self._create_homework()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/",
            json.dumps({"state": "XX"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_homework_invalid_field(self):
        hw = self._create_homework()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/",
            json.dumps({"id": 999}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_homework_closed(self):
        hw = self._create_homework(state=HomeworkState.CLOSED.value)
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Homework.objects.filter(id=hw.id).exists())

    def test_delete_homework_not_closed(self):
        hw = self._create_homework(state=HomeworkState.OPEN.value)
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Homework.objects.filter(id=hw.id).exists())
