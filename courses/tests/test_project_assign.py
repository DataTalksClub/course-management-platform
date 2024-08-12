import logging

from collections import defaultdict

from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
    PeerReview,
    PeerReviewState,
)

from courses.projects import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)


logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectActionsTestCase(TestCase):
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

    def generate_submissions(self, num_submissions):
        submissions = []

        for i in range(num_submissions):
            student = User.objects.create_user(
                username=f"student_{i}",
                email=f"email_{i}@email.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=student,
                course=self.course,
            )
            submission = ProjectSubmission.objects.create(
                project=self.project,
                student=student,
                enrollment=enrollment,
                github_link=f"https://github.com/{student.username}/project",
            )

            submissions.append(submission)
        return submissions

    def test_select_random_assignment(self):
        num_submissions = 10
        self.generate_submissions(num_submissions)

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        self.assertEqual(peer_reviews.count(), 0)

        self.assertEqual(
            self.project.state,
            ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        status, _ = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.project = fetch_fresh(self.project)
        self.assertEqual(
            self.project.state,
            ProjectState.PEER_REVIEWING.value,
        )

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        peer_reviews = list(peer_reviews)

        expected_num_assignments = (
            num_submissions * self.project.number_of_peers_to_evaluate
        )
        self.assertEqual(len(peer_reviews), expected_num_assignments)

        peer_reviews_by_submission = defaultdict(set)

        for pr in peer_reviews:
            self.assertEqual(pr.state, PeerReviewState.TO_REVIEW.value)
            self.assertEqual(pr.optional, False)
            self.assertIsNone(pr.submitted_at)

            id = pr.submission_under_evaluation.id
            peer_reviews_by_submission[id].add(pr)

        self.assertEqual(
            len(peer_reviews_by_submission), num_submissions
        )

        for _, reviews in peer_reviews_by_submission.items():
            self.assertEqual(
                len(reviews),
                self.project.number_of_peers_to_evaluate,
            )

    def test_select_random_assignment_3_3(self):
        num_submissions = 3
        self.generate_submissions(num_submissions)

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, message = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.FAIL)

        expected_message = "Not enough submissions to assign 3 peer reviews each."
        self.assertEqual(message, expected_message)