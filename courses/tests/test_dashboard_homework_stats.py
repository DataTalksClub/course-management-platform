from django.urls import reverse

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
