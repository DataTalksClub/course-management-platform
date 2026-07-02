from courses.assignment_statistics import (
    calculate_project_statistics,
)
from courses.tests.project_statistics_base import (
    ProjectStatisticsTestBase,
)


class ProjectStatisticsModelTestCase(ProjectStatisticsTestBase):
    def test_calculate_project_statistics_model_creation(self):
        self.create_model_method_submissions()
        statistics_exists = self.project_statistics_exists()
        self.assertFalse(statistics_exists)

        stats = calculate_project_statistics(self.project)

        self.assert_created_project_statistics(stats)

    def test_calculate_project_statistics_force_update(self):
        submissions_data = self.force_update_submission_data()
        self.create_bulk_submissions(submissions_data)
        stats1 = calculate_project_statistics(self.project)
        initial_count = stats1.total_submissions

        self.create_project_submission(
            self.users[3], self.enrollments[3]
        )

        stats2 = calculate_project_statistics(self.project, force=False)
        self.assertEqual(stats2.total_submissions, initial_count)

        stats3 = calculate_project_statistics(self.project, force=True)
        self.assertEqual(stats3.total_submissions, initial_count + 1)

    def test_calculate_project_statistics_uncompleted_project(self):
        incomplete_project = self.create_incomplete_project()

        with self.assertRaises(ValueError) as context:
            calculate_project_statistics(incomplete_project)

        self.assertIn(
            "Cannot calculate statistics for uncompleted project",
            str(context.exception),
        )

    def test_project_statistics_model_methods(self):
        self.create_model_method_submissions()
        stats = calculate_project_statistics(self.project)

        self.assert_statistics_values(stats)
        self.assert_stat_fields_shape(stats)
        self.assert_statistics_string_includes_project(stats)
