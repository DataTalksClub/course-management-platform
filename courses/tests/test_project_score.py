from unittest.mock import patch

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

    def test_project_evaluation_complete_mediam(self):
        answers = ["4", "4", "1"]
        scores = [3, 3, 0]
        expected_project_score = 3

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions(self):
        answers = ["4", "2"]
        scores = [3, 1]
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions_round_up(self):
        answers = ["4", "1"]
        scores = [3, 0]
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_one_submission(self):
        answers = ["4"]
        scores = [3]
        expected_project_score = 3

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_zero_submissions_get_median_score_rounded_up(
        self,
    ):
        answers = []
        scores = []
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
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

    def test_learning_in_public_project(self):
        self.submission.learning_in_public_links = [
            "https://example1.com",
            "https://example2.com",
            "https://example3.com",
        ]
        self.submission.save()

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.project_learning_in_public_score, 3
        )

    def test_learning_in_public_peer_review(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        pr1 = other_prs[0]
        pr1.learning_in_public_links = [
            "https://example1.com",
            "https://example2.com",
            "https://example3.com",
        ]
        self.submit_peer_review(pr1, "4")

        pr2 = other_prs[1]
        pr2.learning_in_public_links = [
            "https://example4.com",
            "https://example5.com",
        ]
        self.submit_peer_review(pr2, "3")

        pr3 = other_prs[2]
        pr3.learning_in_public_links = ["https://example6.com"]
        self.submit_peer_review(pr3, "2")

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()

        self.assertTrue(self.submission.reviewed_enough_peers)

        self.assertEqual(
            self.submission.peer_review_score,
            3 * self.project.points_for_peer_review,
        )

        self.assertEqual(
            self.submission.peer_review_learning_in_public_score,
            3 + 2 + 1,
        )

    def test_project_faq_score_contributed(self):
        self.submission.faq_contribution_url = "https://github.com/DataTalksClub/faq/pull/266"
        self.submission.save()

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.project_faq_score, 1)

    def test_project_faq_score_not_contributed(self):
        self.submission.faq_contribution_url = ""
        self.submission.save()

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.project_faq_score, 0)

    def test_project_passed(self):
        # 3 peers evaluated
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")

        # received good score
        answers = ["4", "4", "1"]
        scores = [3, 3, 0]
        expected_project_score = 3

        self.course.project_passing_score = 3
        self.course.save()

        answers_and_scores = list(zip(answers, scores))

        # also does the scoring
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
        # 3 peers evaluated
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        self.submit_peer_review(other_prs[0], "4")
        self.submit_peer_review(other_prs[1], "3")
        self.submit_peer_review(other_prs[2], "3")

        # received one good score and two bad scores
        answers = ["4", "1", "1"]
        scores = [3, 0, 0]
        expected_project_score = 0

        self.course.project_passing_score = 3
        self.course.save()

        answers_and_scores = list(zip(answers, scores))

        # also does the scoring
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

    def test_not_scoring_when_passing_score_is_0(self):
        self.course.project_passing_score = 0
        self.course.save()

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.FAIL)

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
