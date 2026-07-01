from courses.project_assignment import ProjectActionStatus
from courses.project_scoring import score_project
from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectEvaluationTestCase(ProjectEvaluationTestBase):

    def test_project_evaluation_complete_list_top_score(self):
        answers_and_scores = [("4", 3), ("4", 3), ("3", 2)]
        expected_project_score = 3
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_complete_median(self):
        answers_and_scores = [("4", 3), ("4", 3), ("1", 0)]
        expected_project_score = 3

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions(self):
        answers_and_scores = [("4", 3), ("2", 1)]
        expected_project_score = 2

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions_round_up(self):
        answers_and_scores = [("4", 3), ("1", 0)]
        expected_project_score = 2

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_one_submission(self):
        answers_and_scores = [("4", 3)]
        expected_project_score = 3

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_zero_submissions_get_median_score_rounded_up(
        self,
    ):
        answers_and_scores = []
        expected_project_score = 2

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_not_enough_projects_evaluated(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        pr1 = other_prs[0]
        self.submit_peer_review(pr1, "4")

        pr2 = other_prs[1]
        self.submit_peer_review(pr2, "3")

        # pr3 is not submitted

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()

        self.assertFalse(self.submission.reviewed_enough_peers)
        self.assertFalse(self.submission.passed)

        self.assertEqual(
            self.submission.peer_review_score,
            2 * self.project.points_for_peer_review,
        )

    def test_project_enough_projects_evaluated(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        pr1 = other_prs[0]
        self.submit_peer_review(pr1, "4")

        pr2 = other_prs[1]
        self.submit_peer_review(pr2, "3")

        pr3 = other_prs[2]
        self.submit_peer_review(pr3, "2")

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()

        self.assertTrue(self.submission.reviewed_enough_peers)

        self.assertEqual(
            self.submission.peer_review_score,
            3 * self.project.points_for_peer_review,
        )

    def test_not_scoring_when_passing_score_is_0(self):
        self.course.project_passing_score = 0
        self.course.save()

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.FAIL)
