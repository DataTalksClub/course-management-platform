from courses.project_assignment import ProjectActionStatus
from courses.project_scoring import score_project
from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectScoreBonusTestCase(ProjectEvaluationTestBase):
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
