from django.urls import reverse

from courses.models import (
    PeerReviewState,
    CriteriaResponse,
    ProjectState,
    ProjectVote,
)
from courses.tests.project_eval_base import (
    ProjectEvaluationTestBase,
    credentials,
    fetch_fresh,
)


class ProjectEvaluationTestCase(ProjectEvaluationTestBase):

    def test_eval_submit_not_authenticated(self):
        response = self.client.get(self.eval_submit_url())
        self.assertEqual(response.status_code, 302)

    def test_eval_submit_get_authenticated_not_submitted_accepting_responses(
        self,
    ):
        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])
        self.assertFalse(context["disabled"])

        course = context["course"]
        self.assertEqual(course, self.course)

        project = context["project"]
        self.assertEqual(project, self.project)

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.TO_REVIEW.value)

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

        self.assert_empty_criteria_response_pairs(
            context["criteria_response_pairs"]
        )

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

    def test_eval_submit_get_authenticated_not_submitted_not_accepting_responses(
        self,
    ):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )
        self.assertNotContains(
            response,
            'id="submit-button"',
            status_code=200,
        )

        context = response.context

        self.assertFalse(context["accepting_submissions"])
        self.assertTrue(context["disabled"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)

        self.assert_empty_criteria_response_pairs(
            context["criteria_response_pairs"]
        )

    def test_eval_submit_post_not_accepting_responses(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        response = self.post_eval_submit(self.review_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )

        self.peer_review = fetch_fresh(self.peer_review)
        self.assertEqual(self.peer_review.state, PeerReviewState.TO_REVIEW.value)
        self.assertEqual(self.peer_review.note_to_peer, "")
        self.assertIsNone(self.peer_review.submitted_at)
        self.assertFalse(
            CriteriaResponse.objects.filter(review=self.peer_review).exists()
        )

    def test_eval_submit_get_authenticated_submitted(self):
        criteria_responses = self.create_criteria_responses()
        self.mark_peer_review_submitted()

        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.SUBMITTED.value)

        self.assert_submitted_criteria_response_pairs(
            context["criteria_response_pairs"],
            criteria_responses,
        )

    def learning_in_public_review_links(self):
        return [
            "http://example.com/page",
            "http://example.com/page2",
        ]

    def review_post_data_with_learning_links(self):
        learning_links = self.learning_in_public_review_links()
        extra_fields = {
            "learning_in_public_links[]": learning_links,
        }
        return self.review_post_data(
            **extra_fields,
            problems_comments="No problems",
        )

    def assert_learning_in_public_links_saved(self, expected_links):
        learning_in_public_links = (
            self.peer_review.learning_in_public_links
        )
        self.assertEqual(len(learning_in_public_links), len(expected_links))
        for index, expected_link in enumerate(expected_links):
            self.assertEqual(
                learning_in_public_links[index],
                expected_link,
            )

    def test_eval_submit_post_not_submitted(self):
        criteria_responses = self.criteria_responses()
        self.assertEqual(criteria_responses.count(), 0)

        post_data = self.review_post_data_with_learning_links()
        response = self.post_eval_submit(post_data)

        self.assertEqual(response.status_code, 302)
        expected_answers = {
            self.criteria1: "1",
            self.criteria2: "2",
            self.criteria3: "1,3",
        }
        self.assert_review_saved(expected_answers)
        self.assertEqual(self.peer_review.problems_comments, "No problems")

        expected_links = self.learning_in_public_review_links()
        self.assert_learning_in_public_links_saved(expected_links)

    def test_eval_submit_post_already_submitted(self):
        criteria_response_map = self.create_criteria_responses()
        self.mark_peer_review_submitted()
        criteria_responses = self.criteria_responses()
        self.assertEqual(criteria_responses.count(), 3)

        response = self.post_eval_submit(self.updated_review_post_data())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(criteria_responses.count(), 3)

        c1 = fetch_fresh(criteria_response_map[self.criteria1])
        self.assertEqual(c1.answer, "2")

        c2 = fetch_fresh(criteria_response_map[self.criteria2])
        self.assertEqual(c2.answer, "3")

        c3 = fetch_fresh(criteria_response_map[self.criteria3])
        self.assertEqual(c3.answer, "1,2,3")

    def test_eval_submit_page_can_vote_for_reviewed_submission(self):
        self.client.login(**credentials)

        url = reverse(
            "projects_eval_submit",
            args=[self.course.slug, self.project.slug, self.peer_review.id],
        )
        response = self.client.post(
            url,
            {
                "form_action": "vote",
                "submission_id": self.other_submission.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProjectVote.objects.filter(
                voter=self.user,
                submission=self.other_submission,
            ).exists()
        )
