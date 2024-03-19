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
)


logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
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
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
        )

        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link=f"https://github.com/user/project",
            commit_id="1234567",
        )

        self.other_user = User.objects.create_user(
            username=f"student",
            email=f"email@email.com",
            password="12345",
        )

        self.other_enrollment = Enrollment.objects.create(
            student=self.other_user,
            course=self.course,
        )

        self.other_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.other_user,
            enrollment=self.other_enrollment,
            github_link=f"https://github.com/other_student/project",
            commit_id="1234567",
        )

        self.peer_review = PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            optional=False,
        )

    def test_test(self):
        self.assertEqual(1, 1)