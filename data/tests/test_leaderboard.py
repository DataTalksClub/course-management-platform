"""Tests for the public leaderboard data endpoint."""

from dataclasses import dataclass

import yaml
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from accounts.models import CustomUser
from courses.models import (
    Course,
    Enrollment,
    Homework,
    Submission,
    Project,
    ProjectSubmission,
)
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState
from courses.leaderboard import update_leaderboard


@dataclass(frozen=True)
class LeaderboardEnrollmentData:
    user: CustomUser
    display_name: str
    total_score: int
    position: int


class LeaderboardDataViewTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.course = self.create_course()
        self.url = self.course_leaderboard_url()
        self.user1 = self.create_user("user1")
        self.user2 = self.create_user("user2")
        enrollment_data = LeaderboardEnrollmentData(
            user=self.user1,
            display_name="Alice",
            total_score=100,
            position=1,
        )
        self.enrollment1 = self.create_leaderboard_enrollment(
            enrollment_data
        )
        enrollment_data = LeaderboardEnrollmentData(
            user=self.user2,
            display_name="Bob",
            total_score=50,
            position=2,
        )
        self.enrollment2 = self.create_leaderboard_enrollment(
            enrollment_data
        )

    def create_course(self):
        return Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def course_leaderboard_url(self):
        return reverse(
            "api_course_leaderboard",
            kwargs={"course_slug": self.course.slug},
        )

    def create_user(self, username):
        return CustomUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            password="pw",
        )

    def create_leaderboard_enrollment(
        self,
        data,
    ):
        return Enrollment.objects.create(
            student=data.user,
            course=self.course,
            display_name=data.display_name,
            total_score=data.total_score,
            position_on_leaderboard=data.position,
        )

    def tearDown(self):
        cache.clear()

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

    def test_response_is_cached(self):
        self.client.get(self.url)

        # Modify data - cached response should still be old
        self.enrollment1.display_name = "Alice Changed"
        self.enrollment1.save()

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")

    def create_paginated_leaderboard_entries(self):
        for i in range(3, 106):
            user = CustomUser.objects.create(
                username=f"user{i}", email=f"user{i}@example.com"
            )
            Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"User {i}",
                total_score=100 - i,
                position_on_leaderboard=i,
            )

    def leaderboard_data(self, params=None):
        if params is None:
            params = {}
        response = self.client.get(self.url, params)
        data = yaml.safe_load(response.content)
        return data

    def assert_first_leaderboard_page(self, data):
        self.assertEqual(data["page"], 1)
        self.assertNotIn("page_size", data)
        self.assertEqual(data["total_entries"], 105)
        self.assertEqual(data["total_pages"], 2)
        self.assertTrue(data["has_next"])
        self.assertEqual(
            data["next_page"],
            "/api/courses/test-course/leaderboard.yaml?page=2",
        )
        self.assertEqual(data["next_page_number"], 2)
        self.assertEqual(len(data["leaderboard"]), 100)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")
        self.assertEqual(data["leaderboard"][-1]["display_name"], "User 100")

    def assert_second_leaderboard_page(self, data):
        self.assertEqual(data["page"], 2)
        self.assertEqual(len(data["leaderboard"]), 5)
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])
        self.assertIsNone(data["next_page_number"])
        self.assertEqual(
            data["previous_page"],
            "/api/courses/test-course/leaderboard.yaml?page=1",
        )
        self.assertEqual(data["previous_page_number"], 1)
        self.assertEqual(data["leaderboard"][0]["display_name"], "User 101")

    def test_leaderboard_is_paginated(self):
        self.create_paginated_leaderboard_entries()

        first_page_data = self.leaderboard_data()
        self.assert_first_leaderboard_page(first_page_data)

        second_page_data = self.leaderboard_data({"page": 2})
        self.assert_second_leaderboard_page(second_page_data)

    def test_rendered_yaml_response_is_cached(self):
        self.client.get(self.url)

        with patch("api.views.leaderboard_exports.yaml.dump") as yaml_dump:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        yaml_dump.assert_not_called()

    def test_cache_invalidation(self):
        self.client.get(self.url)

        self.enrollment1.display_name = "Alice Changed"
        self.enrollment1.save()
        update_leaderboard(self.course)

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice Changed")

    def test_nonexistent_course(self):
        response = self.client.get(
            "/api/courses/nonexistent/leaderboard.yaml"
        )
        self.assertEqual(response.status_code, 404)
