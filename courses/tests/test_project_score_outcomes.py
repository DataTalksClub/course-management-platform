from unittest.mock import patch

from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectScoreOutcomeTestCase(ProjectEvaluationTestBase):
    def test_project_passed(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")

        answers = ["4", "4", "1"]
        scores = [3, 3, 0]
        expected_project_score = 3

        self.course.project_passing_score = 3
        self.course.save()

        answers_and_scores = list(zip(answers, scores))

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.passed)

        self.assertEqual(
            self.submission.project_score, expected_project_score
        )
        self.assertEqual(
            self.submission.peer_review_score,
            3 * self.project.points_for_peer_review,
        )
        self.assertEqual(
            self.submission.total_score,
            expected_project_score
            + 3 * self.project.points_for_peer_review,
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
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")

        answers = ["4", "1", "1"]
        scores = [3, 0, 0]
        expected_project_score = 0

        self.course.project_passing_score = 3
        self.course.save()

        answers_and_scores = list(zip(answers, scores))

        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

        self.submission.refresh_from_db()
        self.assertFalse(self.submission.passed)

        self.assertEqual(
            self.submission.project_score, expected_project_score
        )
        self.assertEqual(
            self.submission.peer_review_score,
            3 * self.project.points_for_peer_review,
        )
        self.assertEqual(
            self.submission.total_score,
            expected_project_score
            + 3 * self.project.points_for_peer_review,
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

        expected_project_score = 3
        self.course.project_passing_score = 3
        self.course.save()

        self.assert_evaluation_score(
            [("4", 3), ("4", 3), ("1", 0)],
            expected_project_score,
        )
        self.assert_passed_with_peer_review_scores(
            expected_project_score,
            len(other_prs),
        )
