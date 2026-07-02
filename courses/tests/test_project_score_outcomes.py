from unittest.mock import patch

from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectScoreOutcomeTestCase(ProjectEvaluationTestBase):
    def submit_required_reverse_reviews(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)
        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")
        return other_prs

    def use_three_point_project_passing_score(self):
        self.course.project_passing_score = 3
        self.course.save()

    def assert_project_score_outcome(
        self,
        expected_project_score,
        expected_passed,
        review_count,
    ):
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.passed, expected_passed)
        self.assertEqual(
            self.submission.project_score, expected_project_score
        )
        self.assertEqual(
            self.submission.peer_review_score,
            review_count * self.project.points_for_peer_review,
        )
        self.assertEqual(
            self.submission.total_score,
            expected_project_score
            + review_count * self.project.points_for_peer_review,
        )

    def test_project_passed(self):
        other_prs = self.submit_required_reverse_reviews()
        review_count = len(other_prs)
        expected_project_score = 3
        self.use_three_point_project_passing_score()
        answers_and_scores = [("4", 3), ("4", 3), ("1", 0)]

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

        self.assert_project_score_outcome(
            expected_project_score,
            expected_passed=True,
            review_count=review_count,
        )

    @patch("courses.project_scoring._sync_scored_project_submission_to_datamailer")
    def test_project_scoring_syncs_datamailer_after_commit(self, sync):
        other_prs = self.create_reverse_assignments(self.peer_reviews)
        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")
        answers_and_scores = [("4", 3), ("4", 3), ("3", 2)]

        with self.captureOnCommitCallbacks(execute=True):
            self.assert_evaluation_score(answers_and_scores, 3)

        self.assertEqual(sync.call_count, 4)
        synced_submission_ids = set()
        sync_calls = sync.call_args_list
        for call in sync_calls:
            submission_id = call.args[0].pk
            synced_submission_ids.add(submission_id)
        self.assertIn(self.submission.pk, synced_submission_ids)

    def test_project_not_passed(self):
        other_prs = self.submit_required_reverse_reviews()
        review_count = len(other_prs)
        expected_project_score = 0
        self.use_three_point_project_passing_score()
        answers_and_scores = [("4", 3), ("1", 0), ("1", 0)]

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

        self.assert_project_score_outcome(
            expected_project_score,
            expected_passed=False,
            review_count=review_count,
        )

    def test_project_passed_with_optional(self):
        other_prs = self.submit_reverse_peer_reviews(
            self.peer_reviews,
            ["4", "3", "3"],
        )
        optional_reviews = self.create_peer_reviews(2, optional=True)
        self.submit_reverse_peer_reviews(
            optional_reviews,
            ["4", "3"],
            optional=True,
        )
        review_count = len(other_prs)

        expected_project_score = 3
        self.course.project_passing_score = 3
        self.course.save()

        self.assert_evaluation_score(
            [("4", 3), ("4", 3), ("1", 0)],
            expected_project_score,
        )
        self.assert_passed_with_peer_review_scores(
            expected_project_score,
            review_count,
        )
