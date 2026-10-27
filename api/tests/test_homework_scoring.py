from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

from api.tests.homework_api_base import HomeworkAPITestBase
from courses.models.homework import HomeworkState
from courses.models.scoring_job import ScoringJob


class HomeworkScoringAPITestCase(HomeworkAPITestBase):
    def drain_scoring_queue(self):
        call_command("process_scoring_queue")

    def test_score_homework_queues_and_worker_scores(self):
        homework = self._create_scoreable_homework()
        question = self._create_scored_question(homework)
        submission = self._create_answered_submission(homework, question)
        url = self._homework_score_url(homework)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_status"], "queued")
        self.assertIn("job_id", data)
        self.assertIn("poll_url", data)
        # Request returns immediately: nothing scored yet.
        submission.refresh_from_db()
        self.assertEqual(submission.total_score, 0)

        self.drain_scoring_queue()

        status_response = self.client.get(url)
        self.assertEqual(status_response.status_code, 200)
        status_data = status_response.json()
        self.assertEqual(status_data["job_status"], "succeeded")
        self.assertEqual(status_data["state"], HomeworkState.SCORED.value)
        self.assertEqual(status_data["rescored_submissions_count"], 1)
        submission.refresh_from_db()
        self.assertEqual(submission.total_score, 2)

    def test_duplicate_score_posts_share_one_job(self):
        homework = self._create_scoreable_homework()
        question = self._create_scored_question(homework)
        self._create_answered_submission(homework, question)
        url = self._homework_score_url(homework)

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        self.assertEqual(
            ScoringJob.objects.filter(homework=homework).count(), 1
        )

        self.drain_scoring_queue()
        homework.refresh_from_db()
        self.assertEqual(homework.state, HomeworkState.SCORED.value)

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
