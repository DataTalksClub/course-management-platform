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


from courses.projects import score_project, ProjectActionStatus

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
            faq_contribution="AAAAAAAAAA"
        )

        self.criteria = ReviewCriteria.objects.create(
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

        self.peer_reviews = []

        for i in range(3):
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
            pr = PeerReview.objects.create(
                submission_under_evaluation=self.submission,
                reviewer=other_submission,
                state=PeerReviewState.TO_REVIEW.value,
            )
            self.peer_reviews.append(pr)

    def test_project_evaluation(self):
        answers = ["4", "4", "3"] 

        for pr, answer in zip(self.peer_reviews, answers):
            CriteriaResponse.objects.create(
                review=pr,
                criteria=self.criteria,
                answer=answer,
            )
            pr.state = PeerReviewState.SUBMITTED.value
            pr.save()
        

        status, message = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)
        
