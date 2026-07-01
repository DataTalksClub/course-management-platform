from datetime import timedelta
from collections import defaultdict

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectSubmission,
    ProjectState,
    User,
)
from courses.project_assignment import assign_peer_reviews_for_project


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


class ProjectActionsTestBase(TestCase):
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
        submission_due_date = timezone.now() - timedelta(hours=1)
        peer_review_due_date = timezone.now() + timedelta(hours=1)
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
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
            github_link = f"https://github.com/{student.username}/project"
            submission = ProjectSubmission.objects.create(
                project=self.project,
                student=student,
                enrollment=enrollment,
                github_link=github_link,
            )
            submissions.append(submission)
        return submissions

    def create_my_submission(self):
        github_link = f"https://github.com/{self.user.username}/project"
        return ProjectSubmission.objects.create(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
            github_link=github_link,
        )

    def assign_peer_reviews(self):
        return assign_peer_reviews_for_project(self.project)

    def project_peer_reviews(self):
        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        return list(peer_reviews)

    def assert_no_peer_reviews(self):
        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        peer_review_count = peer_reviews.count()
        self.assertEqual(peer_review_count, 0)

    def assert_assignment_created(self, num_submissions):
        self.project = fetch_fresh(self.project)
        self.assertEqual(
            self.project.state,
            ProjectState.PEER_REVIEWING.value,
        )
        peer_reviews = self.project_peer_reviews()
        expected_num_assignments = (
            num_submissions * self.project.number_of_peers_to_evaluate
        )
        self.assertEqual(len(peer_reviews), expected_num_assignments)
        self.assert_peer_reviews_distributed(peer_reviews, num_submissions)

    def assert_peer_reviews_distributed(self, peer_reviews, num_submissions):
        peer_reviews_by_submission = defaultdict(set)
        for peer_review in peer_reviews:
            self.assertEqual(
                peer_review.state,
                PeerReviewState.TO_REVIEW.value,
            )
            self.assertEqual(peer_review.optional, False)
            self.assertIsNone(peer_review.submitted_at)
            submission_id = peer_review.submission_under_evaluation.id
            peer_reviews_by_submission[submission_id].add(peer_review)

        self.assertEqual(len(peer_reviews_by_submission), num_submissions)
        for reviews in peer_reviews_by_submission.values():
            self.assertEqual(
                len(reviews),
                self.project.number_of_peers_to_evaluate,
            )

    def project_list_url(self):
        return reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

    def add_eval_url(self, submission_id):
        return reverse(
            "projects_eval_add",
            args=[
                self.course.slug,
                self.project.slug,
                submission_id,
            ],
        )

    def delete_eval_url(self, peer_review_id):
        return reverse(
            "projects_eval_delete",
            args=[
                self.course.slug,
                self.project.slug,
                peer_review_id,
            ],
        )

    def projects_eval_url(self):
        return reverse(
            "projects_eval",
            args=[
                self.course.slug,
                self.project.slug,
            ],
        )

    def find_optional_eval_candidate_id(self):
        url = self.project_list_url()
        list_response = self.client.get(url)
        self.assertEqual(list_response.status_code, 200)
        for submission in list_response.context["submissions"]:
            if not submission.to_evaluate and not submission.own:
                return submission.id
        self.fail("No submission to evaluate found.")

    def get_peer_review(self, reviewer, submission):
        return PeerReview.objects.get(
            reviewer=reviewer,
            submission_under_evaluation=submission,
        )

    def create_peer_review(self, reviewer, submission, *, optional):
        return PeerReview.objects.create(
            reviewer=reviewer,
            submission_under_evaluation=submission,
            optional=optional,
        )

    def add_optional_eval_and_assert_redirect(self, submission):
        self.client.login(**credentials)
        url = self.add_eval_url(submission.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def assert_optional_peer_review_created(self, reviewer, submission):
        peer_review = self.get_peer_review(reviewer, submission)
        self.assertEqual(peer_review.optional, True)

    def assert_no_peer_review(self, reviewer, submission):
        peer_reviews = PeerReview.objects.filter(
            reviewer=reviewer,
            submission_under_evaluation=submission,
        )
        peer_review_exists = peer_reviews.exists()
        self.assertFalse(peer_review_exists)

    def delete_peer_review_response(self, peer_review):
        self.client.login(**credentials)
        url = self.delete_eval_url(peer_review.id)
        return self.client.get(url)

    def assert_peer_review_deleted(self, peer_review):
        reviews = PeerReview.objects.filter(id=peer_review.id)
        peer_review_exists = reviews.exists()
        self.assertFalse(peer_review_exists)

    def assert_peer_review_still_exists(self, peer_review):
        reviews = PeerReview.objects.filter(id=peer_review.id)
        peer_review_exists = reviews.exists()
        self.assertTrue(peer_review_exists)
