from dataclasses import dataclass

import yaml
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from courses.models import Course, Enrollment


@dataclass(frozen=True)
class LeaderboardEnrollmentData:
    user: CustomUser
    display_name: str
    total_score: int
    position: int


class LeaderboardDataViewBase(TestCase):
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

    def leaderboard_data(self, params=None):
        if params is None:
            params = {}
        response = self.client.get(self.url, params)
        data = yaml.safe_load(response.content)
        return data
