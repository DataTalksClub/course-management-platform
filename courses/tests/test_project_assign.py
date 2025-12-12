import logging

from datetime import timedelta
from collections import defaultdict

from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

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

        expected_message = (
            "Not enough submissions to assign 3 peer reviews each."
        )
        self.assertEqual(message, expected_message)

    def test_select_random_assignment_4_3(self):
        """Test assignment with 4 submissions and 3 peer reviews each."""
        num_submissions = 4
        self.generate_submissions(num_submissions)

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, message = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        # Should have 4 * 3 = 12 peer reviews
        self.assertEqual(peer_reviews.count(), 12)

    def test_add_optional_project_eval_flow(self):
        num_submissions = 10
        self.generate_submissions(num_submissions)

        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, message = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.client.login(**credentials)

        project_list_url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        list_response = self.client.get(project_list_url)
        self.assertEqual(list_response.status_code, 200)

        list_context = list_response.context
        submissions = list_context["submissions"]

        for submission in submissions:
            if not submission.to_evaluate:
                other_submission_id = submission.id
                break
        else:
            self.assertTrue(False, "No submission to evaluate found.")

        eval_url = reverse(
            "projects_eval_add",
            args=[
                self.course.slug,
                self.project.slug,
                other_submission_id,
            ],
        )
        self.client.get(eval_url)

        other_submission = ProjectSubmission.objects.get(
            id=other_submission_id
        )
        peer_review = PeerReview.objects.get(
            reviewer=my_submission,
            submission_under_evaluation=other_submission,
        )

        self.assertEqual(peer_review.optional, True)
        self.assertEqual(
            peer_review.state, PeerReviewState.TO_REVIEW.value
        )

    def test_add_optional_project_eval(self):
        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        num_submissions = 5
        other_submissions = self.generate_submissions(num_submissions)
        other_submission = other_submissions[0]

        self.client.login(**credentials)

        eval_url = reverse(
            "projects_eval_add",
            args=[
                self.course.slug,
                self.project.slug,
                other_submission.id,
            ],
        )

        response = self.client.get(eval_url)
        self.assertEqual(response.status_code, 302)

        peer_review = PeerReview.objects.get(
            reviewer=my_submission,
            submission_under_evaluation=other_submission,
        )

        self.assertEqual(peer_review.optional, True)

    def test_add_optional_project_self_eval_not_possible(self):
        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        num_submissions = 5
        self.generate_submissions(num_submissions)
        other_submission = my_submission

        self.client.login(**credentials)

        eval_url = reverse(
            "projects_eval_add",
            args=[
                self.course.slug,
                self.project.slug,
                other_submission.id,
            ],
        )

        response = self.client.get(eval_url)
        self.assertEqual(response.status_code, 302)

        peer_reviews = PeerReview.objects.filter(
            reviewer=my_submission,
            submission_under_evaluation=other_submission,
        )

        self.assertFalse(peer_reviews.exists())


    def test_delete_optional_project_eval_non_optional(self):
        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        num_submissions = 5
        other_submissions = self.generate_submissions(num_submissions)
        other_submission = other_submissions[0]

        peer_review = PeerReview.objects.create(
            reviewer=my_submission,
            submission_under_evaluation=other_submission,
            optional=False,
        )

        self.client.login(**credentials)

        delete_url = reverse(
            "projects_eval_delete",
            args=[
                self.course.slug,
                self.project.slug,
                peer_review.id,
            ],
        )

        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 302)

        reviews = PeerReview.objects.filter(id=peer_review.id)

        self.assertTrue(reviews.exists())

    def test_delete_optional_project_eval_optional(self):
        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        num_submissions = 5
        other_submissions = self.generate_submissions(num_submissions)
        other_submission = other_submissions[0]

        peer_review = PeerReview.objects.create(
            reviewer=my_submission,
            submission_under_evaluation=other_submission,
            optional=True,
        )

        self.client.login(**credentials)

        delete_url = reverse(
            "projects_eval_delete",
            args=[
                self.course.slug,
                self.project.slug,
                peer_review.id,
            ],
        )

        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 302)

        reviews = PeerReview.objects.filter(id=peer_review.id)

        self.assertFalse(reviews.exists())

    def test_delete_project_eval_from_other_user(self):
        my_submission = ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=f"https://github.com/{self.user.username}/project",
        )

        num_submissions = 5
        other_submissions = self.generate_submissions(num_submissions)
        other_submission = other_submissions[0]

        peer_review = PeerReview.objects.create(
            reviewer=other_submission,
            submission_under_evaluation=my_submission,
            optional=True,
        )

        self.client.login(**credentials)

        delete_url = reverse(
            "projects_eval_delete",
            args=[
                self.course.slug,
                self.project.slug,
                peer_review.id,
            ],
        )

        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 302)

        reviews = PeerReview.objects.filter(id=peer_review.id)

        self.assertTrue(reviews.exists())
