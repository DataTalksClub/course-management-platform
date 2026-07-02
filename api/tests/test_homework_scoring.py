from datetime import timedelta

from django.utils import timezone

from api.tests.homework_api_base import HomeworkAPITestBase
from courses.models.homework import HomeworkState


class HomeworkScoringAPITestCase(HomeworkAPITestBase):
    def test_score_homework(self):
        homework = self._create_scoreable_homework()
        question = self._create_scored_question(homework)
        submission = self._create_answered_submission(homework, question)
        url = self._homework_score_url(homework)

        response = self.client.post(url)

        self._assert_homework_score_response(response)
        submission.refresh_from_db()
        self.assertEqual(submission.total_score, 2)

    def test_score_homework_by_slug_blocked_when_closed(self):
        homework = self._create_homework(
            slug="closed-hw",
            state=HomeworkState.CLOSED.value,
        )
        homework.due_date = timezone.now() - timedelta(hours=1)
        homework.save()

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
        homework = self._create_homework(state=HomeworkState.OPEN.value)
        client = self._non_staff_client("nonstaff")

        response = client.post(
            f"/api/courses/{self.course.slug}/homeworks/{homework.id}/score/"
        )

        self._assert_staff_token_required(response)
