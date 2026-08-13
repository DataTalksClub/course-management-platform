import json

from django.apps import apps
from django.test import Client

from api.tests.project_api_base import ProjectAPITestBase
from courses.models import (
    CriteriaResponse,
    PeerReview,
    PeerReviewState,
    ReviewCriteria,
    ReviewCriteriaTypes,
)


class ProjectSystemEvaluationAPITestCase(ProjectAPITestBase):
    def setUp(self):
        super().setUp()
        self.course.project_passing_score = 2
        self.course.save()
        self.project = self._create_project(slug="system-evaluation")
        self.submission = self._create_project_submission(
            self.project,
            "evaluated-student",
        )
        self.criteria = ReviewCriteria.objects.create(
            course=self.course,
            description="Project quality",
            options=[
                {"criteria": "Needs work", "score": 0},
                {"criteria": "Meets expectations", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        self.url = (
            f"/api/courses/{self.course.slug}/projects/by-slug/"
            f"{self.project.slug}/submissions/{self.submission.id}/"
            "system-evaluations/"
        )
        self.payload = {
            "idempotency_key": "support-issue-123-attempt-1",
            "feedback": "The project is complete and clearly documented.",
            "criteria_responses": [
                {"criteria_id": self.criteria.id, "answer": "2"},
            ],
        }

    def post_evaluation(self, payload=None, client=None):
        return (client or self.client).post(
            self.url,
            json.dumps(payload or self.payload),
            content_type="application/json",
        )

    def test_staff_token_can_create_system_evaluation(self):
        response = self.post_evaluation()

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["submission_id"], self.submission.id)
        self.assertEqual(data["feedback"], self.payload["feedback"])
        self.assertEqual(data["created_by_user_id"], self.user.id)
        self.assertEqual(
            data["criteria_responses"],
            [
                {
                    "criteria_id": self.criteria.id,
                    "answer": "2",
                    "score": 2,
                }
            ],
        )

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.project_score, 2)
        self.assertEqual(self.submission.total_score, 2)

        evaluation_model = apps.get_model(
            "courses", "SystemProjectEvaluation"
        )
        self.assertEqual(evaluation_model.objects.count(), 1)

    def test_get_returns_submission_rubric_and_evaluations(self):
        create_response = self.post_evaluation()
        self.assertEqual(create_response.status_code, 201)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["submission"]["id"], self.submission.id)
        self.assertEqual(
            data["submission"]["github_link"],
            self.submission.github_link,
        )
        self.assertEqual(data["criteria"][0]["id"], self.criteria.id)
        self.assertEqual(
            data["criteria"][0]["options"], self.criteria.options
        )
        self.assertEqual(data["peer_evaluations"], [])
        self.assertEqual(len(data["system_evaluations"]), 1)

    def test_create_is_idempotent(self):
        first = self.post_evaluation()
        second = self.post_evaluation()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        evaluation_model = apps.get_model(
            "courses", "SystemProjectEvaluation"
        )
        self.assertEqual(evaluation_model.objects.count(), 1)

    def test_reusing_idempotency_key_for_other_payload_is_rejected(self):
        first = self.post_evaluation()
        changed_payload = dict(self.payload)
        changed_payload["feedback"] = "A different evaluation."

        second = self.post_evaluation(changed_payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "idempotency_conflict")

    def test_system_evaluation_is_added_to_peer_evaluations(self):
        reviewer = self._create_project_submission(
            self.project,
            "peer-reviewer",
        )
        peer_review = PeerReview.objects.create(
            submission_under_evaluation=self.submission,
            reviewer=reviewer,
            state=PeerReviewState.SUBMITTED.value,
        )
        CriteriaResponse.objects.create(
            review=peer_review,
            criteria=self.criteria,
            answer="1",
        )

        response = self.post_evaluation()

        self.assertEqual(response.status_code, 201)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.project_score, 1)

    def test_create_requires_staff_token(self):
        non_staff_client = self._non_staff_client(
            "system-evaluation-nonstaff"
        )

        response = self.post_evaluation(client=non_staff_client)

        self._assert_staff_token_required(response)

    def test_create_requires_a_complete_valid_rubric(self):
        payload = dict(self.payload)
        payload["criteria_responses"] = []

        response = self.post_evaluation(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "incomplete_evaluation")

    def test_system_evaluation_is_visible_to_student(self):
        create_response = self.post_evaluation()
        self.assertEqual(create_response.status_code, 201)
        client = Client()
        client.force_login(self.submission.student)

        response = client.get(
            f"/{self.course.slug}/project/{self.project.slug}/results"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System evaluation")
        self.assertContains(response, self.payload["feedback"])
        self.assertNotContains(
            response,
            "No evaluation is available for this submission yet.",
        )
