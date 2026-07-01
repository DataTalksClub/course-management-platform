from courses.models import PeerReview, PeerReviewState, ProjectSubmission
from courses.project_assignment import ProjectActionStatus
from courses.tests.project_assign_base import (
    ProjectActionsTestBase,
    credentials,
)


class ProjectOptionalEvaluationTestCase(ProjectActionsTestBase):
    def test_add_optional_project_eval_flow(self):
        num_submissions = 10
        self.generate_submissions(num_submissions)

        my_submission = self.create_my_submission()

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, _ = self.assign_peer_reviews()
        self.assertEqual(status, ProjectActionStatus.OK)

        self.client.login(**credentials)
        other_submission_id = self.find_optional_eval_candidate_id()
        other_submission = ProjectSubmission.objects.get(
            id=other_submission_id
        )

        self.add_optional_eval_and_assert_redirect(other_submission)

        peer_review = self.get_peer_review(my_submission, other_submission)

        self.assertEqual(peer_review.optional, True)
        self.assertEqual(
            peer_review.state, PeerReviewState.TO_REVIEW.value
        )

    def test_add_optional_project_eval(self):
        my_submission = self.create_my_submission()

        num_submissions = 5
        other_submissions = self.generate_submissions(num_submissions)
        other_submission = other_submissions[0]

        self.add_optional_eval_and_assert_redirect(other_submission)
        self.assert_optional_peer_review_created(
            my_submission,
            other_submission,
        )

    def test_add_optional_project_self_eval_not_possible(self):
        my_submission = self.create_my_submission()

        num_submissions = 5
        self.generate_submissions(num_submissions)

        self.add_optional_eval_and_assert_redirect(my_submission)
        self.assert_no_peer_review(my_submission, my_submission)

    def test_delete_optional_project_eval_non_optional(self):
        my_submission = self.create_my_submission()
        other_submission = self.generate_submissions(5)[0]
        peer_review = self.create_peer_review(
            my_submission,
            other_submission,
            optional=False,
        )

        self.client.login(**credentials)

        delete_url = self.delete_eval_url(peer_review.id)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 302)
        redirect_url = self.projects_eval_url()
        self.assertRedirects(
            response,
            redirect_url,
            fetch_redirect_response=False,
        )

        peer_review_exists = PeerReview.objects.filter(
            id=peer_review.id
        ).exists()
        self.assertTrue(peer_review_exists)

    def test_delete_optional_project_eval_optional(self):
        my_submission = self.create_my_submission()
        other_submissions = self.generate_submissions(5)
        other_submission = other_submissions[0]
        peer_review = self.create_peer_review(
            my_submission,
            other_submission,
            optional=True,
        )

        response = self.delete_peer_review_response(peer_review)
        self.assertEqual(response.status_code, 302)

        self.assert_peer_review_deleted(peer_review)

    def test_delete_project_eval_from_other_user(self):
        my_submission = self.create_my_submission()
        other_submissions = self.generate_submissions(5)
        other_submission = other_submissions[0]
        peer_review = self.create_peer_review(
            other_submission,
            my_submission,
            optional=True,
        )

        response = self.delete_peer_review_response(peer_review)
        self.assertEqual(response.status_code, 302)

        self.assert_peer_review_still_exists(peer_review)
