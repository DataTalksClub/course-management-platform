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
        url = self._url()
        response = self.client.get(url)
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
        url = self._url()
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
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
        url = self._url()
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 2)

    def test_create_question_missing_text(self):
        payload = {"question_type": "FF"}
        url = self._url()
        request_body = json.dumps(payload)
        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_question(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Old text",
            question_type="FF",
        )
        url = self._url(q.id)
        patch_payload = {"text": "New text", "scores_for_correct_answer": 3}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
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

        url = self._url(q.id)
        response = self.client.get(url)

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
        url = self._url(q.id)
        patch_payload = {"possible_answers": ["A", "B", "C"]}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        q.refresh_from_db()
        possible_answers = q.get_possible_answers()
        self.assertEqual(possible_answers, ["A", "B", "C"])

    def test_patch_question_invalid_field(self):
        q = Question.objects.create(
            homework=self.homework,
            text="Q?",
            question_type="FF",
        )
        url = self._url(q.id)
        patch_payload = {"id": 999}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
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
        url = self._url(q.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        question_exists = Question.objects.filter(id=q.id).exists()
        self.assertFalse(question_exists)

    def create_answered_question(self):
        question = Question.objects.create(
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

    def test_delete_question_with_answers_is_blocked(self):
        question, answer = self.create_answered_question()

        url = self._url(question.id)
        response = self.client.delete(url)

        self.assert_question_delete_blocked_response(response)
        self.assert_answered_question_exists(question, answer)

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
        create_url = self._url()
        create_body = json.dumps(create_payload)
        create_response = client.post(
            create_url,
            create_body,
            content_type="application/json",
        )
        responses.append(create_response)

        patch_payload = {"text": "Changed by nonstaff"}
        patch_url = self._url(question.id)
        patch_body = json.dumps(patch_payload)
        patch_response = client.patch(
            patch_url,
            patch_body,
            content_type="application/json",
        )
        responses.append(patch_response)

        delete_url = self._url(question.id)
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

    def test_question_mutations_require_staff_token(self):
        question = Question.objects.create(
            homework=self.homework,
            text="Staff only question",
            question_type="FF",
        )
        client = self.non_staff_client()

        responses = self.non_staff_mutation_responses(client, question)

        for response in responses:
            self.assert_staff_token_required(response)
        self.assert_question_unchanged_after_forbidden_mutations(question)
