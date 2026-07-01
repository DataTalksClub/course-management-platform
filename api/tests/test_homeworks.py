import json

from courses.models import (
    Homework,
    Question,
    Submission,
)
from courses.models.homework import HomeworkState
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

    def _create_homework_with_old_question(self):
        homework = self._create_homework(slug="hw-put")
        Question.objects.create(
            homework=homework,
            text="Old question",
            question_type="FF",
        )

        return homework

    def _homework_replacement_payload(self):
        return {
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

    def _assert_homework_questions_replaced(self, homework):
        homework.refresh_from_db()
        self.assertEqual(homework.title, "Updated Homework")
        questions = list(homework.question_set.order_by("id"))
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].text, "New question?")

    def test_put_homework_by_slug_updates_and_replaces_questions(self):
        homework = self._create_homework_with_old_question()
        payload = self._homework_replacement_payload()
        payload_body = json.dumps(payload)

        response = self.client.put(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/hw-put/",
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
        submission = self._create_homework_submission(hw)

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
