import logging

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
)


logger = logging.getLogger(__name__)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectSubmissionsViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

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
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        # Create a submission
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc1234",
            project_score=100,
            peer_review_score=50,
            project_faq_score=10,
            project_learning_in_public_score=5,
        )

    def project_submissions_url(self, project=None):
        return reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": (project or self.project).slug,
            },
        )

    def project_url(self):
        return reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def create_user_submission(
        self, index, score=90, commit_id=None
    ):
        user = User.objects.create_user(
            username=f"user{index}@test.com",
            email=f"user{index}@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link=f"https://github.com/test/repo{index}",
            commit_id=commit_id or f"commit{index}",
            project_score=score,
        )

    def create_peer_review(self, submission, state):
        from courses.models import PeerReview, PeerReviewState

        return PeerReview.objects.create(
            submission_under_evaluation=submission,
            reviewer=self.submission,
            state=state,
            optional=False,
        )

    def create_peer_review_completion_fixture(self):
        from courses.models import PeerReviewState

        submission2 = self.create_user_submission(
            2,
            score=90,
            commit_id="def5678",
        )
        submission3 = self.create_user_submission(
            3,
            score=85,
            commit_id="ghi9012",
        )
        self.create_peer_review(submission2, PeerReviewState.SUBMITTED.value)
        self.create_peer_review(submission3, PeerReviewState.TO_REVIEW.value)

    def admin_submissions_response(self, project=None):
        self.login_admin()
        return self.client.get(
            self.project_submissions_url(project),
            follow=True,
        )

    def submission_for_user(self, response, user):
        submissions = list(response.context["submissions"])
        return [
            submission for submission in submissions
            if submission.student == user
        ][0]

    def assert_peer_review_completion(self, response):
        user_submission = self.submission_for_user(response, self.user)
        self.assertEqual(user_submission.peer_reviews_completed, 1)
        self.assertEqual(user_submission.peer_reviews_total, 2)

    def test_submissions_view_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected"""
        response = self.client.get(self.project_submissions_url())

        # Should redirect to project view with error message
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "project",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
        )

    def test_submissions_view_regular_user_denied(self):
        """Test that regular users cannot access submissions view"""
        self.client.login(**credentials)
        response = self.client.get(self.project_submissions_url())

        # Should redirect to project view with error message
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "project",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
        )

    def test_submissions_view_admin_can_access(self):
        """Test that admin users can access submissions view"""
        response = self.admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "cadmin/project_submissions.html")

        context = response.context
        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["project"], self.project)

        submissions = list(context["submissions"])
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0], self.submission)

    def test_submissions_view_displays_all_submissions(self):
        """Test that all submissions are displayed"""
        self.create_user_submission(2, score=90, commit_id="def5678")

        response = self.admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        submissions = list(response.context["submissions"])
        self.assertEqual(len(submissions), 2)

    def test_admin_link_visible_to_staff(self):
        """Test that the admin link is visible to staff users"""
        self.login_admin()
        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Manage project in cadmin"
        )
        self.assertContains(
            response,
            reverse(
                "cadmin_project_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
        )

    def test_admin_link_not_visible_to_regular_users(self):
        """Test that the admin link is not visible to regular users"""
        self.client.login(**credentials)
        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "Manage project in cadmin"
        )

    def test_peer_review_completion_displayed(self):
        """Test that peer review completion is displayed correctly"""
        self.create_peer_review_completion_fixture()

        response = self.admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assert_peer_review_completion(response)

    def test_copy_emails_button_present(self):
        """Test that the copy emails button is present for admin users"""
        response = self.admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        # Check that the copy button is present
        self.assertContains(response, 'id="copyEmailsBtn"')
        self.assertContains(response, 'Copy All Emails')
        # Check that the feedback span is present
        self.assertContains(response, 'id="copyFeedback"')

    def test_copy_emails_button_not_present_when_no_submissions(self):
        """Test that the copy emails button is not present when there are no submissions"""
        # Create a new project with no submissions
        new_project = Project.objects.create(
            course=self.course,
            slug="empty-project",
            title="Empty Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        
        response = self.admin_submissions_response(new_project)

        self.assertEqual(response.status_code, 200)
        # Check that the copy button is not present
        self.assertNotContains(response, 'id="copyEmailsBtn"')
