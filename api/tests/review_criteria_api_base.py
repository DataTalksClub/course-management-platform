import json

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectEvaluationScore,
    ProjectSubmission,
    ReviewCriteria,
    ReviewCriteriaTypes,
)


class ReviewCriteriaAPITestBase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )
        now = timezone.now()
        self.project = Project.objects.create(
            course=self.course,
            title="Test Project",
            slug="test-project",
            submission_due_date=now + timezone.timedelta(days=7),
            peer_review_due_date=now + timezone.timedelta(days=14),
        )

    def criteria_url(self, criteria_id=None):
        base = f"/api/courses/{self.course.slug}/review-criteria/"
        if criteria_id:
            return f"{base}{criteria_id}/"
        return base

    def criteria_payload(self, **overrides):
        payload = {
            "description": "Code quality",
            "review_criteria_type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
            "options": [
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 2},
            ],
        }
        payload.update(overrides)
        return payload

    def create_criteria(self, **overrides):
        payload = self.criteria_payload(**overrides)
        return ReviewCriteria.objects.create(
            course=self.course,
            description=payload["description"],
            review_criteria_type=payload["review_criteria_type"],
            options=payload["options"],
        )

    def create_scored_criteria(self):
        criteria = self.create_criteria()
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/example/repo",
            commit_id="1234567",
        )
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=criteria,
            score=2,
        )
        return criteria

    def non_staff_client(self):
        non_staff = CustomUser.objects.create(
            username="criteria-nonstaff",
            email="criteria-nonstaff@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def non_staff_mutation_responses(self, client, criteria):
        responses = []
        create_response = client.post(
            self.criteria_url(),
            json.dumps(self.criteria_payload()),
            content_type="application/json",
        )
        responses.append(create_response)

        patch_response = client.patch(
            self.criteria_url(criteria.id),
            json.dumps({"description": "Changed by nonstaff"}),
            content_type="application/json",
        )
        responses.append(patch_response)

        delete_response = client.delete(self.criteria_url(criteria.id))
        responses.append(delete_response)
        return responses

    def assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")
