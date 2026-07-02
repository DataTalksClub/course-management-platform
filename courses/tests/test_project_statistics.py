from courses.assignment_statistics import (
    calculate_raw_project_statistics,
)
from courses.tests.project_statistics_base import (
    ProjectStatisticsTestBase,
)


class ProjectStatisticsRawTestCase(ProjectStatisticsTestBase):
    def test_calculate_raw_project_statistics_basic(self):
        self.create_basic_raw_statistics_submissions()

        stats = calculate_raw_project_statistics(self.project)

        self.assertEqual(stats["total_submissions"], 3)
        self.assert_basic_project_score_stats(stats)
        self.assert_basic_total_score_stats(stats)
        self.assert_basic_time_spent_stats(stats)

    def test_calculate_raw_project_statistics_insufficient_data(self):
        for i in range(2):
            self.create_project_submission(
                self.users[i], self.enrollments[i]
            )

        stats = calculate_raw_project_statistics(self.project)

        self.assertEqual(stats["total_submissions"], 2)

        for field in ("project_score", "total_score", "time_spent"):
            self.assertIsNone(stats[field]["min"])
            self.assertIsNone(stats[field]["max"])
            self.assertIsNone(stats[field]["avg"])
            self.assertIsNone(stats[field]["q1"])
            self.assertIsNone(stats[field]["median"])
            self.assertIsNone(stats[field]["q3"])

    def test_calculate_raw_project_statistics_with_nulls(self):
        self.create_null_time_spent_submissions()

        stats = calculate_raw_project_statistics(self.project)

        self.assert_non_null_time_spent_stats(stats)
        self.assert_project_score_includes_null_time_rows(stats)
