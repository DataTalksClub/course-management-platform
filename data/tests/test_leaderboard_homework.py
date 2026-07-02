"""Tests for homework data in the public leaderboard endpoint."""

from django.utils import timezone

from courses.models import Homework, Submission
from courses.models.homework import HomeworkState

from .leaderboard_base import LeaderboardDataViewBase


def create_homework(test_case, title, slug, state):
    homework_due_date = timezone.now()
    return Homework.objects.create(
        course=test_case.course,
        title=title,
        slug=slug,
        description="",
        due_date=homework_due_date,
        state=state,
    )


def create_scored_homework_submission(test_case):
    homework = create_homework(
        test_case,
        title="HW1",
        slug="hw1",
        state=HomeworkState.SCORED.value,
    )
    return Submission.objects.create(
        homework=homework,
        student=test_case.user1,
        enrollment=test_case.enrollment1,
        questions_score=5,
        faq_score=1,
        faq_contribution_url="https://github.com/DataTalksClub/faq/pull/266",
        learning_in_public_score=2,
        total_score=8,
    )


def create_unscored_homework_submission(test_case):
    homework = create_homework(
        test_case,
        title="Open HW",
        slug="open-hw",
        state=HomeworkState.OPEN.value,
    )
    return Submission.objects.create(
        homework=homework,
        student=test_case.user1,
        enrollment=test_case.enrollment1,
        total_score=5,
    )


def assert_scored_homework_export(test_case, homework_data):
    test_case.assertEqual(homework_data["homework"], "HW1")
    test_case.assertEqual(homework_data["questions_score"], 5)
    test_case.assertEqual(homework_data["faq_score"], 1)
    test_case.assertEqual(homework_data["learning_in_public_score"], 2)
    test_case.assertEqual(homework_data["total_score"], 8)
    test_case.assertEqual(
        homework_data["faq_contribution_url"],
        "https://github.com/DataTalksClub/faq/pull/266",
    )


class LeaderboardHomeworkDataViewTestCase(LeaderboardDataViewBase):
    def test_includes_scored_homework_submissions(self):
        create_scored_homework_submission(self)

        data = self.leaderboard_data()

        alice = data["leaderboard"][0]
        self.assertIn("homeworks", alice)
        self.assertEqual(len(alice["homeworks"]), 1)
        homework_data = alice["homeworks"][0]
        assert_scored_homework_export(self, homework_data)

    def test_excludes_unscored_homework(self):
        create_unscored_homework_submission(self)

        data = self.leaderboard_data()

        alice = data["leaderboard"][0]
        self.assertNotIn("homeworks", alice)
