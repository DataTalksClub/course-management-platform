import json

from courses.models import Homework, Question
from api.tests.homework_api_base import (
    HOMEWORK_INSTRUCTIONS_URL,
    HomeworkAPITestBase,
)


class HomeworkMutationAPITestCase(HomeworkAPITestBase):
    def test_patch_homework_state(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"state": "OP"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "OP")
        hw.refresh_from_db()
        self.assertEqual(hw.state, "OP")

    def test_get_homework_detail(self):
        hw = self._create_homework()

        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], hw.id)
        self.assertEqual(data["slug"], "hw1")
        self.assertTrue(data["can_delete"])

    def test_patch_homework_by_slug(self):
        self._create_homework(slug="hw-by-slug")

        url = (
            f"/api/courses/{self.course.slug}/homeworks/by-slug/"
            "hw-by-slug/"
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
        self.assertEqual(data["slug"], "hw-by-slug")

    def test_put_homework_by_slug_creates_homework(self):
        question = {
            "text": "Question one?",
            "question_type": "FF",
        }
        questions = []
        questions.append(question)
        payload = {
            "name": "Homework From Put",
            "due_date": "2026-04-01T23:59:59Z",
            "description": "Created idempotently",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            "questions": questions,
        }

        url = f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/"
        request_body = json.dumps(payload)
        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "hw-put")
        self.assertEqual(data["title"], "Homework From Put")
        self.assertEqual(data["questions_count"], 1)

    def _create_homework_with_old_question(self):
        homework = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=homework,
            text="Old question",
            question_type="FF",
        )

        return homework

    def _homework_replacement_payload(self):
        possible_answers = ["A", "B"]
        question = {
            "text": "New question?",
            "question_type": "MC",
            "possible_answers": possible_answers,
            "correct_answer": "1",
        }
        questions = []
        questions.append(question)
        return {
            "title": "Updated Homework",
            "due_date": "2026-04-01T23:59:59Z",
            "questions": questions,
        }

    def _assert_homework_questions_replaced(self, homework):
        homework.refresh_from_db()
        self.assertEqual(homework.title, "Updated Homework")
        ordered_questions = homework.question_set.order_by("id")
        questions = list(ordered_questions)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].text, "New question?")

    def test_put_homework_by_slug_updates_and_replaces_questions(self):
        homework = self._create_homework_with_old_question()
        payload = self._homework_replacement_payload()
        payload_body = json.dumps(payload)

        url = f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/"
        response = self.client.put(
            url,
            payload_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self._assert_homework_questions_replaced(homework)

    def test_put_homework_questions_with_submissions_is_blocked(self):
        hw = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=hw,
            text="Old question",
            question_type="FF",
        )
        self._create_homework_submission(hw)
        question = {"text": "New question?", "question_type": "FF"}
        questions = []
        questions.append(question)
        payload = {
            "title": "Should Not Update",
            "questions": questions,
        }

        url = f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/"
        request_body = json.dumps(payload)
        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"],
            "homework_questions_replace_blocked",
        )
        hw.refresh_from_db()
        self.assertEqual(hw.title, "Homework 1")

    def test_put_homework_invalid_state_does_not_create(self):
        payload = {
            "name": "Bad State",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            "state": "XX",
        }
        url = f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/"
        request_body = json.dumps(payload)
        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "invalid_homework_state"
        )
        homework_exists = Homework.objects.filter(
            course=self.course, slug="hw-put"
        ).exists()
        self.assertFalse(homework_exists)

    def test_patch_homework_description(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"description": "Updated"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        hw.refresh_from_db()
        self.assertEqual(hw.description, "Updated")

    def test_patch_homework_invalid_state(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"state": "XX"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_homework_invalid_field(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"id": 999}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
