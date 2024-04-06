import logging

from django.urls import reverse
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    Enrollment,
    PeerReview,
    PeerReviewState,
    CriteriaResponse,
    ReviewCriteria,
    ReviewCriteriaTypes,
    ProjectState,
)


logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectEvaluationTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(days=2),
            peer_review_due_date=timezone.now() - timedelta(hours=1),
            state=ProjectState.PEER_REVIEWING.value,
            points_for_peer_review=10,
            learning_in_public_cap_project=5,
            learning_in_public_cap_review=3,
            number_of_peers_to_evaluate=2,
            points_to_pass=70,
        )

        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/user/project",
            commit_id="1234567",
            learning_in_public_links=["link1", "link2", "link3"],
            faq_contribution="A"*10,  # Assume this means they've contributed enough to FAQ
        )


        self.criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Satisfactory", "score": 1},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Project documentation",
            options=[
                {"criteria": "None", "score": 0},
                {"criteria": "Basic", "score": 1},
                {"criteria": "Complete", "score": 2},
                {"criteria": "In-depth", "score": 3},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.criteria3 = ReviewCriteria.objects.create(
            course=self.course,
            description="Best practices",
            options=[
                {"criteria": "Coding standards", "score": 1},
                {"criteria": "Tests", "score": 1},
                {"criteria": "Logging", "score": 1},
                {"criteria": "Version control", "score": 1},
                {"criteria": "CI/CD", "score": 1},
            ],
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

        self.criteria = [self.criteria1, self.criteria2, self.criteria3]

        # Create additional users for peer reviews
        for i in range(1, 4):
            other_user = User.objects.create_user(
                username=f"student{i}",
                email=f"student{i}@email.com",
                password="12345",
            )
            other_enrollment = Enrollment.objects.create(
                student=other_user,
                course=self.course,
            )
            other_submission = ProjectSubmission.objects.create(
                project=self.project,
                student=other_user,
                enrollment=other_enrollment,
                github_link=f"https://github.com/other_student{i}/project",
                commit_id="abcdefg{i}",
            )

            peer_review = PeerReview.objects.create(
                submission_under_evaluation=other_submission,
                reviewer=self.submission,
                state=PeerReviewState.SUBMITTED.value,
            )

            for criteria in self.criteria:
                CriteriaResponse.objects.create(
                    review=peer_review,
                    criteria=criteria,
                    answer="1"
                )


    def test_project_evaluation(self):
        pass