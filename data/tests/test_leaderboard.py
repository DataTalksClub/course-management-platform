"""Tests for the public leaderboard data endpoint."""

import yaml
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from accounts.models import CustomUser, Token
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
from courses.scoring import update_leaderboard


class LeaderboardDataViewTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )
        self.url = reverse(
            "api_course_leaderboard",
            kwargs={"course_slug": self.course.slug},
        )

        self.user1 = CustomUser.objects.create(
            username="user1", email="user1@example.com", password="pw",
        )
        self.user2 = CustomUser.objects.create(
            username="user2", email="user2@example.com", password="pw",
        )
        self.enrollment1 = Enrollment.objects.create(
            student=self.user1,
            course=self.course,
            display_name="Alice",
            total_score=100,
            position_on_leaderboard=1,
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.user2,
            course=self.course,
            display_name="Bob",
            total_score=50,
            position_on_leaderboard=2,
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
        hw = Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.SCORED.value,
        )
        Submission.objects.create(
            homework=hw,
            student=self.user1,
            enrollment=self.enrollment1,
            questions_score=5,
            faq_score=1,
            learning_in_public_score=2,
            total_score=8,
        )

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        alice = data["leaderboard"][0]
        self.assertIn("homeworks", alice)
        self.assertEqual(len(alice["homeworks"]), 1)
        self.assertEqual(alice["homeworks"][0]["homework"], "HW1")
        self.assertEqual(alice["homeworks"][0]["questions_score"], 5)
        self.assertEqual(alice["homeworks"][0]["faq_score"], 1)
        self.assertEqual(alice["homeworks"][0]["learning_in_public_score"], 2)
        self.assertEqual(alice["homeworks"][0]["total_score"], 8)

    def test_excludes_unscored_homework(self):
        hw = Homework.objects.create(
            course=self.course,
            title="Open HW",
            slug="open-hw",
            description="",
            due_date=timezone.now(),
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

    def test_includes_completed_project_submissions(self):
        proj = Project.objects.create(
            course=self.course,
            title="Project 1",
            slug="project-1",
            description="",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=ProjectState.COMPLETED.value,
        )
        ProjectSubmission.objects.create(
            project=proj,
            student=self.user1,
            enrollment=self.enrollment1,
            project_score=80,
            peer_review_score=9,
            project_learning_in_public_score=3,
            peer_review_learning_in_public_score=1,
            project_faq_score=1,
            total_score=94,
            passed=True,
        )

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        alice = data["leaderboard"][0]
        self.assertIn("projects", alice)
        self.assertEqual(len(alice["projects"]), 1)
        self.assertEqual(alice["projects"][0]["project_score"], 80)
        self.assertTrue(alice["projects"][0]["passed"])

    def test_response_is_cached(self):
        self.client.get(self.url)

        # Modify data - cached response should still be old
        self.enrollment1.display_name = "Alice Changed"
        self.enrollment1.save()

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")

    def test_leaderboard_is_paginated(self):
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

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)

        self.assertEqual(data["page"], 1)
        self.assertNotIn("page_size", data)
        self.assertEqual(data["total_entries"], 105)
        self.assertEqual(data["total_pages"], 2)
        self.assertTrue(data["has_next"])
        self.assertEqual(data["next_page"], 2)
        self.assertEqual(len(data["leaderboard"]), 100)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")
        self.assertEqual(data["leaderboard"][-1]["display_name"], "User 100")

        response = self.client.get(self.url, {"page": 2})
        data = yaml.safe_load(response.content)

        self.assertEqual(data["page"], 2)
        self.assertEqual(len(data["leaderboard"]), 5)
        self.assertFalse(data["has_next"])
        self.assertEqual(data["previous_page"], 1)
        self.assertEqual(data["leaderboard"][0]["display_name"], "User 101")

    def test_rendered_yaml_response_is_cached(self):
        self.client.get(self.url)

        with patch("data.views.leaderboard.yaml.dump") as yaml_dump:
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
