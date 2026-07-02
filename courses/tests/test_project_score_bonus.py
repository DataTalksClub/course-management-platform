from courses.project_assignment import ProjectActionStatus
from courses.project_scoring import score_project
from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectScoreBonusTestCase(ProjectEvaluationTestBase):
    def assert_project_scored(self):
        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

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

    def submit_peer_review_with_links(self, peer_review, links, answer):
        peer_review.learning_in_public_links = links
        self.submit_peer_review(peer_review, answer)

    def submit_peer_reviews_with_learning_links(self, peer_reviews):
        first_links = [
            "https://example1.com",
            "https://example2.com",
            "https://example3.com",
        ]
        self.submit_peer_review_with_links(peer_reviews[0], first_links, "4")

        second_links = [
            "https://example4.com",
            "https://example5.com",
        ]
        self.submit_peer_review_with_links(peer_reviews[1], second_links, "3")

        third_links = ["https://example6.com"]
        self.submit_peer_review_with_links(peer_reviews[2], third_links, "2")

    def assert_peer_review_bonus_scores(self):
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.reviewed_enough_peers)

        expected_peer_review_score = 3 * self.project.points_for_peer_review
        self.assertEqual(
            self.submission.peer_review_score,
            expected_peer_review_score,
        )

        expected_learning_in_public_score = 3 + 2 + 1
        self.assertEqual(
            self.submission.peer_review_learning_in_public_score,
            expected_learning_in_public_score,
        )

    def test_learning_in_public_peer_review(self):
        other_prs = self.create_reverse_assignments(self.peer_reviews)

        self.submit_peer_reviews_with_learning_links(other_prs)
        self.assert_project_scored()
        self.assert_peer_review_bonus_scores()

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
