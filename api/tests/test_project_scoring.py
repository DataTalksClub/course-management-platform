from datetime import timedelta

from django.utils import timezone

from api.tests.project_api_base import ProjectAPITestBase
from courses.models import PeerReview
from courses.models.project import PeerReviewState, ProjectState


class ProjectScoringAPITestCase(ProjectAPITestBase):
    def create_project_ready_for_scoring(self):
        self.course.project_passing_score = 1
        self.course.save()
        project = self._create_project(
            state=ProjectState.PEER_REVIEWING.value
        )
        project.peer_review_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.number_of_peers_to_evaluate = 1
        project.save()
        return project

    def create_submitted_peer_reviews(self, project):
        submission_1 = self._create_project_submission(
            project, "score-student-1"
        )
        submission_2 = self._create_project_submission(
            project, "score-student-2"
        )
        PeerReview.objects.create(
            submission_under_evaluation=submission_1,
            reviewer=submission_2,
            state=PeerReviewState.SUBMITTED.value,
        )
        PeerReview.objects.create(
            submission_under_evaluation=submission_2,
            reviewer=submission_1,
            state=PeerReviewState.SUBMITTED.value,
        )

    def assert_project_scored_response(self, response):
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["project_slug"], "proj1")
        self.assertEqual(data["state"], ProjectState.COMPLETED.value)
        self.assertEqual(data["submissions_count"], 2)
        self.assertEqual(data["scored_submissions_count"], 2)

    def test_score_project(self):
        project = self.create_project_ready_for_scoring()
        self.create_submitted_peer_reviews(project)

        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/score/"
        )

        self.assert_project_scored_response(response)

    def test_score_project_by_slug_blocked_without_peer_reviews(self):
        self.course.project_passing_score = 1
        self.course.save()
        project = self._create_project(
            slug="no-reviews-project",
            state=ProjectState.PEER_REVIEWING.value,
        )
        project.peer_review_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.save()

        response = self.client.post(
            (
                f"/api/courses/{self.course.slug}/projects/by-slug/"
                "no-reviews-project/score/"
            )
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["project_slug"], "no-reviews-project")
        self.assertEqual(
            data["state"], ProjectState.PEER_REVIEWING.value
        )
        self.assertEqual(data["scored_submissions_count"], 0)
