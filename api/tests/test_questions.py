import json

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Answer, Course, Enrollment, Homework, Question, Submission
from courses.models.homework import HomeworkState


class QuestionsAPITestCase(TestCase):

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
        self.homework = Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.CLOSED.value,
        )

    def _url(self, question_id=None):
        base = (
            f"/api/courses/{self.course.slug}/homeworks/"
            f"{self.homework.id}/questions/"
        )
        if question_id:
            return f"{base}{question_id}/"
        return base

    def test_list_questions(self):
        Question.objects.create(
            homework=self.homework,
            text="Q1?",
            question_type="FF",
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions"]), 1)
        self.assertEqual(data["questions"][0]["answers_count"], 0)
        self.assertTrue(data["questions"][0]["can_delete"])

    def test_create_question(self):
        payload = {
            "text": "What is 2+2?",
            "question_type": "MC",
            "possible_answers": ["3", "4", "5"],
            "correct_answer": "2",
        }
        response = self.client.post(
            self._url(),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["created"][0]["text"], "What is 2+2?")

    def test_create_question_bulk(self):
        payload = [
            {"text": "Q1?", "question_type": "FF"},
            {"text": "Q2?", "question_type": "FF"},
        ]
        response = self.client.post(
            self._url(),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 2)

    def test_create_question_missing_text(self):
        payload = {"question_type": "FF"}
        response = self.client.post(
            self._url(),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_question(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Old text",
            question_type="FF",
        )
        response = self.client.patch(
            self._url(q.id),
            json.dumps({"text": "New text", "scores_for_correct_answer": 3}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        q.refresh_from_db()
        self.assertEqual(q.text, "New text")
        self.assertEqual(q.scores_for_correct_answer, 3)

    def test_get_question_detail(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Question detail",
            question_type="FF",
        )

        response = self.client.get(self._url(q.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], q.id)
        self.assertEqual(data["answers_count"], 0)
        self.assertTrue(data["can_delete"])

    def test_patch_question_possible_answers_as_list(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Q?",
            question_type="MC",
        )
        response = self.client.patch(
            self._url(q.id),
            json.dumps({"possible_answers": ["A", "B", "C"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        q.refresh_from_db()
        self.assertEqual(q.get_possible_answers(), ["A", "B", "C"])

    def test_patch_question_invalid_field(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Q?",
            question_type="FF",
        )
        response = self.client.patch(
            self._url(q.id),
            json.dumps({"id": 999}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")

    def test_delete_question(self):
        q = Question.objects.create(
            homework=self.homework,
            text="To delete",
            question_type="FF",
        )
        response = self.client.delete(self._url(q.id))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Question.objects.filter(id=q.id).exists())

    def test_delete_question_with_answers_is_blocked(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Answered question",
            question_type="FF",
        )
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=enrollment,
        )
        answer = Answer.objects.create(
            submission=submission,
            question=q,
            answer_text="answer",
        )

        response = self.client.delete(self._url(q.id))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete question with existing answers",
        )
        self.assertEqual(response.json()["code"], "question_has_answers")
        self.assertEqual(response.json()["details"]["answers_count"], 1)
        self.assertTrue(Question.objects.filter(id=q.id).exists())
        self.assertTrue(Answer.objects.filter(id=answer.id).exists())
