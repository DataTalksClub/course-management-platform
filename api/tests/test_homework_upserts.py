import json

from courses.models import Homework, Question
from api.tests.homework_api_base import (
    HOMEWORK_INSTRUCTIONS_URL,
    HomeworkAPITestBase,
)


class HomeworkBySlugUpsertTestBase(HomeworkAPITestBase):
    def by_slug_url(self):
        return f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/"

    def create_homework_with_old_question(self):
        homework = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=homework,
            text="Old question",
            question_type="FF",
        )

        return homework

    def homework_replacement_payload(self):
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

    def assert_homework_questions_replaced(self, homework):
        homework.refresh_from_db()
        self.assertEqual(homework.title, "Updated Homework")
        ordered_questions = homework.question_set.order_by("id")
        questions = list(ordered_questions)
        questions_count = len(questions)
        self.assertEqual(questions_count, 1)
        self.assertEqual(questions[0].text, "New question?")


class HomeworkBySlugCreateAPITestCase(HomeworkBySlugUpsertTestBase):
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

        url = self.by_slug_url()
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


class HomeworkBySlugQuestionReplacementAPITestCase(
    HomeworkBySlugUpsertTestBase,
):
    def test_put_homework_by_slug_updates_and_replaces_questions(self):
        homework = self.create_homework_with_old_question()
        payload = self.homework_replacement_payload()
        payload_body = json.dumps(payload)

        url = self.by_slug_url()
        response = self.client.put(
            url,
            payload_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assert_homework_questions_replaced(homework)

    def test_put_homework_questions_with_submissions_is_blocked(self):
        homework = self.create_homework_with_old_question()
        self._create_homework_submission(homework)
        question = {"text": "New question?", "question_type": "FF"}
        questions = []
        questions.append(question)
        payload = {
            "title": "Should Not Update",
            "questions": questions,
        }

        url = self.by_slug_url()
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
        homework.refresh_from_db()
        self.assertEqual(homework.title, "Homework 1")


class HomeworkBySlugValidationAPITestCase(HomeworkBySlugUpsertTestBase):
    def test_put_homework_invalid_state_does_not_create(self):
        payload = {
            "name": "Bad State",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            "state": "XX",
        }
        url = self.by_slug_url()
        request_body = json.dumps(payload)
        response = self.client.put(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_homework_state")
        homework_exists = Homework.objects.filter(
            course=self.course, slug="hw-put"
        ).exists()
        self.assertFalse(homework_exists)
