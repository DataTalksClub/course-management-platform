import json
from datetime import timedelta

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


HOMEWORK_INSTRUCTIONS_URL = (
    "https://github.com/DataTalksClub/test/blob/main/homework.md"
)


class HomeworkAPITestBase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def _create_homework(
        self, slug="hw1", state=HomeworkState.CLOSED.value
    ):
        due_date = timezone.now()
        return Homework.objects.create(
            course=self.course,
            title="Homework 1",
            slug=slug,
            description="Description",
            instructions_url=HOMEWORK_INSTRUCTIONS_URL,
            due_date=due_date,
            state=state,
        )

    def _non_staff_client(self, username):
        non_staff = CustomUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def _create_scoreable_homework(self):
        homework = self._create_homework(state=HomeworkState.OPEN.value)
        homework.due_date = timezone.now() - timedelta(hours=1)
        homework.save()
        return homework

    def _create_scored_question(self, homework):
        return Question.objects.create(
            homework=homework,
            text="What is 2+2?",
            question_type="FF",
            answer_type="EXS",
            correct_answer="4",
            scores_for_correct_answer=2,
        )

    def _create_homework_submission(self, homework):
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        return Submission.objects.create(
            homework=homework,
            student=self.user,
            enrollment=enrollment,
        )

    def _create_answered_submission(self, homework, question):
        submission = self._create_homework_submission(homework)
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text="4",
        )
        return submission

    def _homework_score_url(self, homework):
        return f"/api/courses/{self.course.slug}/homeworks/{homework.id}/score/"

    def _assert_homework_score_response(self, response):
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["homework_slug"], "hw1")
        self.assertEqual(data["state"], HomeworkState.SCORED.value)
        self.assertEqual(data["submissions_count"], 1)
        self.assertEqual(data["rescored_submissions_count"], 1)

    def _non_staff_homework_mutation_responses(self, client, homework):
        create_response = self._non_staff_homework_create_response(client)
        patch_response = self._non_staff_homework_patch_response(
            client, homework
        )
        put_response = self._non_staff_homework_put_response(client)
        delete_response = self._non_staff_homework_delete_response(
            client, homework
        )
        return create_response, patch_response, put_response, delete_response

    def _non_staff_homework_create_response(self, client):
        create_payload = {
            "name": "Created by nonstaff",
            "due_date": "2026-04-01T23:59:59Z",
        }
        create_body = json.dumps(create_payload)
        return client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            create_body,
            content_type="application/json",
        )

    def _non_staff_homework_patch_response(self, client, homework):
        patch_payload = {"description": "Changed by nonstaff"}
        patch_body = json.dumps(patch_payload)
        return client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{homework.id}/",
            patch_body,
            content_type="application/json",
        )

    def _non_staff_homework_put_response(self, client):
        put_payload = {
            "name": "Put by nonstaff",
            "due_date": "2026-04-01T23:59:59Z",
        }
        put_body = json.dumps(put_payload)
        put_url = (
            f"/api/courses/{self.course.slug}/homeworks/by-slug/"
            "nonstaff-put/"
        )
        return client.put(
            put_url,
            put_body,
            content_type="application/json",
        )

    def _non_staff_homework_delete_response(self, client, homework):
        return client.delete(
            f"/api/courses/{self.course.slug}/homeworks/{homework.id}/"
        )
