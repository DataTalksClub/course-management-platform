from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from courses.models import Homework, HomeworkState, Submission
from courses.tests.dashboard_homework_base import (
    DashboardHomeworkStatsTestBase,
)


class DashboardHomeworkStatsTestCase(DashboardHomeworkStatsTestBase):
    def test_homework_statistics_calculation(self):
        self.create_homework_stat_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        hw_stats = response.context["homework_stats"]
        hw_stats_count = len(hw_stats)
        self.assertEqual(hw_stats_count, 1)

        self.assert_homework_stat_summary(hw_stats[0])

    def test_homework_statistics_with_insufficient_data(self):
        for i in range(2):
            self.create_homework_submission(
                self.users[i], self.enrollments[i]
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        self.assertIsNone(hw_stat["time_lecture_q25"])
        self.assertIsNone(hw_stat["time_lecture_median"])
        self.assertIsNone(hw_stat["time_lecture_q75"])
        self.assertEqual(hw_stat["completion_rate"], 40.0)

    def test_homework_statistics_with_null_values(self):
        self.create_null_time_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assert_null_time_homework_stats(
            response.context["homework_stats"][0]
        )

    def test_homework_formatted_time_display(self):
        self.create_formatted_time_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        self.assert_formatted_time_fields(hw_stat)

    def test_homework_statistics_excludes_unscored_homework(self):
        self.create_homework_stat_submissions()

        unscored = Homework.objects.create(
            course=self.course,
            slug="hw2",
            title="Homework 2",
            due_date=timezone.now() + timedelta(days=14),
            state=HomeworkState.OPEN.value,
        )
        for i in range(3):
            Submission.objects.create(
                homework=unscored,
                student=self.users[i],
                enrollment=self.enrollments[i],
                time_spent_lectures=2.0,
                time_spent_homework=3.0,
                total_score=50,
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        titles = [hw_stat["homework"].title for hw_stat in hw_stats]
        self.assertIn("Homework 1", titles)
        self.assertNotIn("Homework 2", titles)
