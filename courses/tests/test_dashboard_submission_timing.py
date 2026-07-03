from datetime import timedelta

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


class DashboardSubmissionTimingTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )
        self.due_date = timezone.now() + timedelta(days=10)
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=self.due_date,
            state=HomeworkState.SCORED.value,
        )

    def create_submission(self, index, days_before):
        user = User.objects.create_user(
            username=f"student{index}@test.com",
            email=f"student{index}@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user, course=self.course
        )
        Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            submitted_at=self.due_date - timedelta(days=days_before),
        )

    def dashboard_url(self):
        return reverse("dashboard", args=[self.course.slug])

    def timing_by_label(self, response):
        return {
            bucket["label"]: bucket
            for bucket in response.context["submission_timing"]
        }

    def test_submission_timing_buckets(self):
        # One submission per bucket.
        self.create_submission(0, days_before=8)
        self.create_submission(1, days_before=5)
        self.create_submission(2, days_before=2)
        self.create_submission(3, days_before=0.5)
        self.create_submission(4, days_before=-1)

        response = self.client.get(self.dashboard_url())

        buckets = self.timing_by_label(response)
        self.assertEqual(buckets["A week or more early"]["count"], 1)
        self.assertEqual(buckets["3-7 days early"]["count"], 1)
        self.assertEqual(buckets["1-3 days early"]["count"], 1)
        self.assertEqual(buckets["Final day"]["count"], 1)
        self.assertEqual(buckets["After the deadline"]["count"], 1)
        self.assertEqual(buckets["Final day"]["pct"], 20.0)
        self.assertContains(response, "Submission timing")

    def test_submission_timing_empty(self):
        response = self.client.get(self.dashboard_url())

        self.assertEqual(response.context["submission_timing"], [])
        self.assertNotContains(response, "Submission timing")
