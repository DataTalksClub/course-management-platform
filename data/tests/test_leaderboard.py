"""Tests for the public leaderboard data endpoint."""

import yaml

from django.utils import timezone

from courses.models import (
    Homework,
    Project,
    ProjectSubmission,
    Submission,
)
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardDataViewTestCase(LeaderboardDataViewBase):

    def test_returns_yaml(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "text/plain; charset=utf-8"
        )
        data = yaml.safe_load(response.content)
        self.assertEqual(data["course"], "test-course")

    def test_no_auth_required(self):
        """Endpoint is public, no token needed."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_ordering(self):
        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        leaderboard = data["leaderboard"]
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["display_name"], "Alice")
        self.assertEqual(leaderboard[0]["total_score"], 100)
        self.assertEqual(leaderboard[0]["position"], 1)
        self.assertEqual(leaderboard[1]["display_name"], "Bob")

    def test_includes_scored_homework_submissions(self):
        homework_due_date = timezone.now()
        homework = Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            due_date=homework_due_date,
            state=HomeworkState.SCORED.value,
        )
        Submission.objects.create(
            homework=homework,
            student=self.user1,
            enrollment=self.enrollment1,
            questions_score=5,
            faq_score=1,
            faq_contribution_url="https://github.com/DataTalksClub/faq/pull/266",
            learning_in_public_score=2,
            total_score=8,
        )

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        alice = data["leaderboard"][0]
        self.assertIn("homeworks", alice)
        self.assertEqual(len(alice["homeworks"]), 1)
        homework_data = alice["homeworks"][0]
        self.assert_scored_homework_export(homework_data)

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

    def test_excludes_unscored_homework(self):
        homework_due_date = timezone.now()
        hw = Homework.objects.create(
            course=self.course,
            title="Open HW",
            slug="open-hw",
            description="",
            due_date=homework_due_date,
            state=HomeworkState.OPEN.value,
        )
        Submission.objects.create(
            homework=hw,
            student=self.user1,
            enrollment=self.enrollment1,
            total_score=5,
        )

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        alice = data["leaderboard"][0]
        self.assertNotIn("homeworks", alice)

    def create_completed_project(self):
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        return Project.objects.create(
            course=self.course,
            title="Project 1",
            slug="project-1",
            description="",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COMPLETED.value,
        )

    def create_completed_project_submission(self):
        project = self.create_completed_project()
        return ProjectSubmission.objects.create(
            project=project,
            student=self.user1,
            enrollment=self.enrollment1,
            project_score=80,
            peer_review_score=9,
            project_learning_in_public_score=3,
            peer_review_learning_in_public_score=1,
            project_faq_score=1,
            faq_contribution_url="https://github.com/DataTalksClub/faq/issues/266",
            total_score=94,
            passed=True,
        )

    def leaderboard_alice(self):
        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        return data["leaderboard"][0]

    def assert_completed_project_export(self, alice):
        self.assertIn("projects", alice)
        self.assertEqual(len(alice["projects"]), 1)
        project = alice["projects"][0]
        self.assertEqual(project["project_score"], 80)
        self.assertEqual(
            project["faq_contribution_url"],
            "https://github.com/DataTalksClub/faq/issues/266",
        )
        self.assertTrue(project["passed"])

    def test_includes_completed_project_submissions(self):
        self.create_completed_project_submission()

        alice = self.leaderboard_alice()

        self.assert_completed_project_export(alice)

    def test_nonexistent_course(self):
        response = self.client.get(
            "/api/courses/nonexistent/leaderboard.yaml"
        )
        self.assertEqual(response.status_code, 404)
