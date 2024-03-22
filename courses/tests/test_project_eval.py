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

    def test_eval_submit_get_authenticated(self):
        """
        Test the evaluation submit view for a GET request by an authenticated user.
        """
        self.client.login(**credentials)
        url = reverse('projects_eval_submit', args=[self.course.slug, self.project.slug, self.peer_review.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('criteria_response_pairs', response.context)
        self.assertIn('submission', response.context)

    # def test_eval_submit_post_authenticated(self):
    #     """
    #     Test the evaluation submit view for a POST request by an authenticated user.
    #     """
    #     self.client.login(**credentials)
    #     url = reverse('projects_eval_submit', args=[self.course.slug, self.project.slug, self.peer_review.id])

    #     response = self.client.post(url, {
    #         'note_to_peer': 'Well done!',
    #         'time_spent_reviewing': '3',
    #         # Assuming criteria IDs start at 1 and you have a set of criteria defined
    #         'answer_1': '4',
    #         'learning_in_public_links[]': ['http://example.com/page']
    #     })

    #     self.peer_review.refresh_from_db()
    #     self.assertEqual(response.status_code, 302)
    #     self.assertEqual(self.peer_review.state, PeerReviewState.SUBMITTED.value)
    #     self.assertEqual(self.peer_review.note_to_peer, 'Well done!')

    #     # Test for presence of CriteriaResponse objects and learning in public links
    #     self.assertEqual(len(self.peer_review.learning_in_public_links), 1)
    #     self.assertEqual(self.peer_review.learning_in_public_links[0], 'http://example.com/page')
    #     self.assertEqual(self.peer_review.time_spent_reviewing, 3.0)
    #     # Check for success message
    #     # messages_list = list(get
                             
    #     # self.assertTrue(any(str(m) == "Thank you for submitting your evaluation, it is now saved. You can update it at any point." for m in messages_list))

    #     # Check if CriteriaResponse objects were created or updated correctly
    #     criteria_responses = CriteriaResponse.objects.filter(review=self.peer_review)
    #     self.assertTrue(criteria_responses.exists())
    #     self.assertEqual(criteria_responses.count(), 1)
    #     self.assertEqual(criteria_responses.first().score, 4)