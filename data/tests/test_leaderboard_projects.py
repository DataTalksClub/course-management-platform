"""Tests for project data in the public leaderboard endpoint."""

from django.utils import timezone

from courses.models import Project, ProjectSubmission
from courses.models.project import ProjectState

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardProjectDataViewTestCase(LeaderboardDataViewBase):
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
        data = self.leaderboard_data()
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
