from courses.scoring import score_homework_submissions

from .scoring_base import HomeworkScoringBase


class HomeworkScoringLeaderboardTests(HomeworkScoringBase):
    def test_leaderboard_update(self):
        data = self.leaderboard_test_data()

        for row in data:
            self.create_answers_for_enrollment(row.enrollment, row.answers)

        score_homework_submissions(self.homework.id)

        self.assert_leaderboard_rows(data)
