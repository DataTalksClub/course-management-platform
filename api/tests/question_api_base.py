import json

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import (
    Answer,
    Course,
    Enrollment,
    Homework,
    Question,
    Submission,
)
from courses.models.homework import HomeworkState


class QuestionAPITestBase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )
        due_date = timezone.now()
        self.homework = Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            due_date=due_date,
            state=HomeworkState.CLOSED.value,
        )

    def question_url(self, question_id=None):
        base = (
            f"/api/courses/{self.course.slug}/homeworks/"
            f"{self.homework.id}/questions/"
        )
        if question_id:
            return f"{base}{question_id}/"
        return base

    def create_question(self, text="Q?", question_type="FF", **overrides):
        defaults = {
            "homework": self.homework,
            "text": text,
            "question_type": question_type,
        }
        defaults.update(overrides)
        return Question.objects.create(**defaults)

    def create_answered_question(self):
        question = self.create_question(
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
            question=question,
            answer_text="answer",
        )

        return question, answer

    def assert_question_delete_blocked_response(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete question with existing answers",
        )
        self.assertEqual(response.json()["code"], "question_has_answers")
        self.assertEqual(response.json()["details"]["answers_count"], 1)

    def assert_answered_question_exists(self, question, answer):
        question_exists = Question.objects.filter(id=question.id).exists()
        answer_exists = Answer.objects.filter(id=answer.id).exists()
        self.assertTrue(question_exists)
        self.assertTrue(answer_exists)

    def non_staff_client(self):
        non_staff = CustomUser.objects.create(
            username="question-nonstaff",
            email="question-nonstaff@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def non_staff_mutation_responses(self, client, question):
        responses = []
        create_payload = {"text": "Created by nonstaff"}
        create_url = self.question_url()
        create_body = json.dumps(create_payload)
        create_response = client.post(
            create_url,
            create_body,
            content_type="application/json",
        )
        responses.append(create_response)

        patch_payload = {"text": "Changed by nonstaff"}
        patch_url = self.question_url(question.id)
        patch_body = json.dumps(patch_payload)
        patch_response = client.patch(
            patch_url,
            patch_body,
            content_type="application/json",
        )
        responses.append(patch_response)

        delete_url = self.question_url(question.id)
        delete_response = client.delete(delete_url)
        responses.append(delete_response)
        return responses

    def assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def assert_question_unchanged_after_forbidden_mutations(self, question):
        question.refresh_from_db()
        self.assertEqual(question.text, "Staff only question")
        question_count = self.homework.question_set.count()
        self.assertEqual(question_count, 1)
