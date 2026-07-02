"""Tests for homework data in the public leaderboard endpoint."""

from django.utils import timezone

from courses.models import Homework, Submission
from courses.models.homework import HomeworkState

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardHomeworkDataFixtureMixin:
    def create_homework(self, title, slug, state):
        homework_due_date = timezone.now()
        return Homework.objects.create(
            course=self.course,
            title=title,
            slug=slug,
            description="",
            due_date=homework_due_date,
            state=state,
        )

    def create_scored_homework_submission(self):
        homework = self.create_homework(
            title="HW1",
            slug="hw1",
            state=HomeworkState.SCORED.value,
        )
        return Submission.objects.create(
            homework=homework,
            student=self.user1,
            enrollment=self.enrollment1,
            questions_score=5,
            faq_score=1,
            faq_contribution_url="https://github.com/DataTalksClub/faq/pull/266",
            learning_in_public_score=2,
            total_score=8,
        )

    def create_unscored_homework_submission(self):
        homework = self.create_homework(
            title="Open HW",
            slug="open-hw",
            state=HomeworkState.OPEN.value,
        )
        return Submission.objects.create(
            homework=homework,
            student=self.user1,
            enrollment=self.enrollment1,
            total_score=5,
        )

    def assert_scored_homework_export(self, homework_data):
        self.assertEqual(homework_data["homework"], "HW1")
        self.assertEqual(homework_data["questions_score"], 5)
        self.assertEqual(homework_data["faq_score"], 1)
        self.assertEqual(homework_data["learning_in_public_score"], 2)
        self.assertEqual(homework_data["total_score"], 8)
        self.assertEqual(
            homework_data["faq_contribution_url"],
            "https://github.com/DataTalksClub/faq/pull/266",
        )


class LeaderboardHomeworkDataViewTestCase(
    LeaderboardHomeworkDataFixtureMixin,
    LeaderboardDataViewBase,
):
    def test_includes_scored_homework_submissions(self):
        self.create_scored_homework_submission()

        data = self.leaderboard_data()

        alice = data["leaderboard"][0]
        self.assertIn("homeworks", alice)
        self.assertEqual(len(alice["homeworks"]), 1)
        homework_data = alice["homeworks"][0]
        self.assert_scored_homework_export(homework_data)

    def test_excludes_unscored_homework(self):
        self.create_unscored_homework_submission()

        data = self.leaderboard_data()

        alice = data["leaderboard"][0]
        self.assertNotIn("homeworks", alice)
