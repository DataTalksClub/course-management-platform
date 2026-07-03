from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Submission,
)

User = get_user_model()


class DashboardEngagementTrendTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=30),
            state=HomeworkState.SCORED.value,
        )
        self._student_index = 0

    def create_submission(self, submitted_at):
        user = User.objects.create_user(
            username=f"student{self._student_index}@test.com",
            email=f"student{self._student_index}@test.com",
            password="12345",
        )
        self._student_index += 1
        enrollment = Enrollment.objects.create(
            student=user, course=self.course
        )
        Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            submitted_at=submitted_at,
        )

    def aware(self, year, month, day):
        # Midday to keep the week bucket stable across timezone truncation.
        return timezone.make_aware(datetime(year, month, day, 12, 0))

    def dashboard_url(self):
        return reverse("dashboard", args=[self.course.slug])

    def test_engagement_trend_weekly_counts(self):
        # Week of Mon Jan 5, 2026: three mid-week submissions.
        self.create_submission(self.aware(2026, 1, 6))
        self.create_submission(self.aware(2026, 1, 7))
        self.create_submission(self.aware(2026, 1, 8))
        # Week of Mon Jan 12, 2026: one submission.
        self.create_submission(self.aware(2026, 1, 14))

        response = self.client.get(self.dashboard_url())

        trend = response.context["engagement_trend"]
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["count"], 3)
        self.assertEqual(trend[0]["bar_pct"], 100.0)
        self.assertEqual(trend[1]["count"], 1)
        self.assertEqual(trend[1]["bar_pct"], 33.3)
        self.assertContains(response, "Engagement over time")

    def test_engagement_trend_empty(self):
        response = self.client.get(self.dashboard_url())

        self.assertEqual(response.context["engagement_trend"], [])
        self.assertNotContains(response, "Engagement over time")
