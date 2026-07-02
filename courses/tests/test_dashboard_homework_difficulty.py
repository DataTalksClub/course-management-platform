from django.urls import reverse

from courses.tests.dashboard_homework_base import (
    DashboardHomeworkStatsTestBase,
)


class DashboardHomeworkDifficultyTestCase(DashboardHomeworkStatsTestBase):
    def test_homework_difficulty_ranking(self):
        self.add_questions(self.homework, 3)
        harder_homework = self.create_homework_for_difficulty(
            "hw2",
            "Homework 2",
            14,
        )
        self.add_questions(harder_homework, 10)
        self.create_difficulty_submissions(harder_homework)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assert_difficulty_ranking(response, harder_homework)
        self.assertContains(response, "Assignment difficulty")
        self.assertContains(response, "Completion")
