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

    def test_submissions_view_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected"""
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

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
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

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
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/submissions.html")

        context = response.context
        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["project"], self.project)

        submissions = list(context["submissions"])
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0], self.submission)

    def test_submissions_view_displays_all_submissions(self):
        """Test that all submissions are displayed"""
        # Create another user and submission
        user2 = User.objects.create_user(
            username="user2@test.com",
            email="user2@test.com",
            password="12345",
        )
        enrollment2 = Enrollment.objects.create(
            student=user2,
            course=self.course,
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=user2,
            enrollment=enrollment2,
            github_link="https://github.com/test/repo2",
            commit_id="def5678",
            project_score=90,
            peer_review_score=45,
            project_faq_score=8,
            project_learning_in_public_score=4,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        submissions = list(response.context["submissions"])
        self.assertEqual(len(submissions), 2)

    def test_admin_link_visible_to_staff(self):
        """Test that the admin link is visible to staff users"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "View all submissions (Admin only)"
        )
        self.assertContains(
            response,
            reverse(
                "project_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
        )

    def test_admin_link_not_visible_to_regular_users(self):
        """Test that the admin link is not visible to regular users"""
        self.client.login(**credentials)
        url = reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "View all submissions (Admin only)"
        )

    def test_peer_review_completion_displayed(self):
        """Test that peer review completion is displayed correctly"""
        from courses.models import PeerReview, PeerReviewState

        # Create another user and submission
        user2 = User.objects.create_user(
            username="user2@test.com",
            email="user2@test.com",
            password="12345",
        )
        enrollment2 = Enrollment.objects.create(
            student=user2,
            course=self.course,
        )
        submission2 = ProjectSubmission.objects.create(
            project=self.project,
            student=user2,
            enrollment=enrollment2,
            github_link="https://github.com/test/repo2",
            commit_id="def5678",
            project_score=90,
        )

        # Create peer reviews for user1
        # user1 reviews user2's submission (completed)
        PeerReview.objects.create(
            submission_under_evaluation=submission2,
            reviewer=self.submission,
            state=PeerReviewState.SUBMITTED.value,
            optional=False,
        )

        # user1 has another review to do (not completed)
        user3 = User.objects.create_user(
            username="user3@test.com",
            email="user3@test.com",
            password="12345",
        )
        enrollment3 = Enrollment.objects.create(
            student=user3,
            course=self.course,
        )
        submission3 = ProjectSubmission.objects.create(
            project=self.project,
            student=user3,
            enrollment=enrollment3,
            github_link="https://github.com/test/repo3",
            commit_id="ghi9012",
            project_score=85,
        )
        PeerReview.objects.create(
            submission_under_evaluation=submission3,
            reviewer=self.submission,
            state=PeerReviewState.TO_REVIEW.value,
            optional=False,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        
        # Check that the page contains the peer review completion data
        submissions = list(response.context["submissions"])
        user1_submission = [s for s in submissions if s.student == self.user][0]
        
        # user1 has completed 1 out of 2 peer reviews
        self.assertEqual(user1_submission.peer_reviews_completed, 1)
        self.assertEqual(user1_submission.peer_reviews_total, 2)

    def test_copy_emails_button_present(self):
        """Test that the copy emails button is present for admin users"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

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
        
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": new_project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check that the copy button is not present
        self.assertNotContains(response, 'id="copyEmailsBtn"')
