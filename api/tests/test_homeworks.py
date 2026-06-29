import json
from datetime import timedelta

from django.test import TestCase, Client
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


class HomeworksAPITestCase(TestCase):
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
        return Homework.objects.create(
            course=self.course,
            title="Homework 1",
            slug=slug,
            description="Description",
            instructions_url=HOMEWORK_INSTRUCTIONS_URL,
            due_date=timezone.now(),
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

    def _non_staff_homework_mutation_responses(self, client, homework):
        create_response = client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps({
                "name": "Created by nonstaff",
                "due_date": "2026-04-01T23:59:59Z",
            }),
            content_type="application/json",
        )
        patch_response = client.patch(
            f"/api/courses/{self.course.slug}/homeworks/{homework.id}/",
            json.dumps({"description": "Changed by nonstaff"}),
            content_type="application/json",
        )
        put_response = client.put(
            (
                f"/api/courses/{self.course.slug}/homeworks/by-slug/"
                "nonstaff-put/"
            ),
            json.dumps({
                "name": "Put by nonstaff",
                "due_date": "2026-04-01T23:59:59Z",
            }),
            content_type="application/json",
        )
        delete_response = client.delete(
            f"/api/courses/{self.course.slug}/homeworks/{homework.id}/"
        )
        return create_response, patch_response, put_response, delete_response

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
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
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
        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/",
            json.dumps(payload),
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
        payload = {
            "name": "HW 1",
            "slug": "hw1",
            "due_date": "2026-04-01T23:59:59Z",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
        }
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

        response = self.client.patch(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-by-slug/",
            json.dumps({"description": "Updated by slug"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Updated by slug")
        self.assertEqual(data["slug"], "hw-by-slug")

    def test_put_homework_by_slug_creates_homework(self):
        payload = {
            "name": "Homework From Put",
            "due_date": "2026-04-01T23:59:59Z",
            "description": "Created idempotently",
            "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
            "questions": [
                {
                    "text": "Question one?",
                    "question_type": "FF",
                }
            ],
        }

        response = self.client.put(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "hw-put")
        self.assertEqual(data["title"], "Homework From Put")
        self.assertEqual(data["questions_count"], 1)

    def test_put_homework_by_slug_updates_and_replaces_questions(self):
        hw = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=hw,
            text="Old question",
            question_type="FF",
        )
        payload = {
            "title": "Updated Homework",
            "due_date": "2026-04-01T23:59:59Z",
            "questions": [
                {
                    "text": "New question?",
                    "question_type": "MC",
                    "possible_answers": ["A", "B"],
                    "correct_answer": "1",
                }
            ],
        }

        response = self.client.put(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        hw.refresh_from_db()
        self.assertEqual(hw.title, "Updated Homework")
        questions = list(hw.question_set.order_by("id"))
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].text, "New question?")

    def test_put_homework_questions_with_submissions_is_blocked(self):
        hw = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=hw,
            text="Old question",
            question_type="FF",
        )
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        Submission.objects.create(
            homework=hw,
            student=self.user,
            enrollment=enrollment,
        )
        payload = {
            "title": "Should Not Update",
            "questions": [
                {"text": "New question?", "question_type": "FF"}
            ],
        }

        response = self.client.put(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/",
            json.dumps(payload),
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
        response = self.client.put(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/",
            json.dumps(
                {
                    "name": "Bad State",
                    "due_date": "2026-04-01T23:59:59Z",
                    "instructions_url": HOMEWORK_INSTRUCTIONS_URL,
                    "state": "XX",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "invalid_homework_state"
        )
        self.assertFalse(
            Homework.objects.filter(
                course=self.course, slug="hw-put"
            ).exists()
        )

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
        self.assertEqual(response.json()["code"], "homework_not_closed")
        self.assertTrue(Homework.objects.filter(id=hw.id).exists())

    def test_delete_homework_with_submissions_is_blocked(self):
        hw = self._create_homework(state=HomeworkState.CLOSED.value)
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = Submission.objects.create(
            homework=hw,
            student=self.user,
            enrollment=enrollment,
        )

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete homework with existing submissions",
        )
        self.assertEqual(
            response.json()["code"], "homework_has_submissions"
        )
        self.assertEqual(
            response.json()["details"]["submissions_count"],
            1,
        )
        self.assertTrue(Homework.objects.filter(id=hw.id).exists())
        self.assertTrue(
            Submission.objects.filter(id=submission.id).exists()
        )

    def test_delete_homework_by_slug_closed_without_submissions(self):
        hw = self._create_homework(slug="draft-hw")

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/draft-hw/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Homework.objects.filter(id=hw.id).exists())

    def test_score_homework(self):
        hw = self._create_homework(state=HomeworkState.OPEN.value)
        hw.due_date = timezone.now() - timedelta(hours=1)
        hw.save()
        question = Question.objects.create(
            homework=hw,
            text="What is 2+2?",
            question_type="FF",
            answer_type="EXS",
            correct_answer="4",
            scores_for_correct_answer=2,
        )
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = Submission.objects.create(
            homework=hw,
            student=self.user,
            enrollment=enrollment,
        )
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text="4",
        )

        response = self.client.post(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/score/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["homework_slug"], "hw1")
        self.assertEqual(data["state"], HomeworkState.SCORED.value)
        self.assertEqual(data["submissions_count"], 1)
        self.assertEqual(data["rescored_submissions_count"], 1)
        submission.refresh_from_db()
        self.assertEqual(submission.total_score, 2)

    def test_score_homework_by_slug_blocked_when_closed(self):
        hw = self._create_homework(
            slug="closed-hw",
            state=HomeworkState.CLOSED.value,
        )
        hw.due_date = timezone.now() - timedelta(hours=1)
        hw.save()

        response = self.client.post(
            (
                f"/api/courses/{self.course.slug}/homeworks/by-slug/"
                "closed-hw/score/"
            )
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["homework_slug"], "closed-hw")
        self.assertEqual(data["state"], HomeworkState.CLOSED.value)
        self.assertEqual(data["rescored_submissions_count"], 0)

    def test_score_homework_requires_staff_token(self):
        hw = self._create_homework(state=HomeworkState.OPEN.value)
        client = self._non_staff_client("nonstaff")

        response = client.post(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/score/"
        )

        self._assert_staff_token_required(response)

    def test_homework_mutations_require_staff_token(self):
        hw = self._create_homework(slug="staff-only-hw")
        client = self._non_staff_client("homework-nonstaff")
        responses = self._non_staff_homework_mutation_responses(
            client, hw
        )

        for response in responses:
            self._assert_staff_token_required(response)

        self.assertFalse(
            Homework.objects.filter(
                course=self.course,
                slug="nonstaff-put",
            ).exists()
        )
        hw.refresh_from_db()
        self.assertEqual(hw.description, "Description")
        self.assertTrue(Homework.objects.filter(id=hw.id).exists())
