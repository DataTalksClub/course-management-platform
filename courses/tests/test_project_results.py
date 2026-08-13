from courses.project_assignment import ProjectActionStatus
from courses.project_scoring import score_project
from courses.models import ProjectEvaluationScore
from courses.tests.project_score_base import ProjectEvaluationTestBase


class ProjectResultsTestCase(ProjectEvaluationTestBase):
    def test_project_results_shows_no_evaluation_when_scores_have_no_responses(self):
        ProjectEvaluationScore.objects.create(
            submission=self.submission,
            review_criteria=self.criteria,
            score=2,
        )

        response = self.project_results_response()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No evaluation is available for this submission yet.",
        )
        score = response.context["scores"][0]
        self.assertEqual(
            [option["votes"] for option in score.option_vote_counts],
            [0, 0, 0, 0],
        )

    def test_project_results_shows_review_option_vote_counts(self):
        checkbox_criteria = self.create_checkbox_criteria()
        self.submit_checkbox_responses(checkbox_criteria)

        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        response = self.project_results_response()

        self.assertEqual(response.status_code, 200)
        self.assert_option_vote_counts(response)
        self.assert_option_vote_content(response)
