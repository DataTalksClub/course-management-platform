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
    PeerReview,
    PeerReviewState,
)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectSubmissionsFixtureMixin:
    def create_admin_user(self):
        return User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def create_project(self):
        now = timezone.now()
        submission_delta = timedelta(days=7)
        peer_review_delta = timedelta(days=14)
        submission_due_date = now + submission_delta
        peer_review_due_date = now + peer_review_delta
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def create_initial_submission(self):
        return ProjectSubmission.objects.create(
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


class ProjectSubmissionsRequestMixin:
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

    def cadmin_project_submissions_url(self):
        return reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def admin_submissions_response(self, project=None):
        self.login_admin()
        submissions_url = self.project_submissions_url(project)
        return self.client.get(
            submissions_url,
            follow=True,
        )


class ProjectSubmissionsDataMixin:
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
        return PeerReview.objects.create(
            submission_under_evaluation=submission,
            reviewer=self.submission,
            state=state,
            optional=False,
        )

    def create_peer_review_completion_fixture(self):
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

    def create_empty_project(self):
        now = timezone.now()
        submission_delta = timedelta(days=7)
        peer_review_delta = timedelta(days=14)
        submission_due_date = now + submission_delta
        peer_review_due_date = now + peer_review_delta
        return Project.objects.create(
            course=self.course,
            slug="empty-project",
            title="Empty Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )


class ProjectSubmissionsPeerReviewMixin:
    def submission_for_user(self, response, user):
        submissions = list(response.context["submissions"])
        for submission in submissions:
            if submission.student == user:
                return submission
        return None

    def assert_peer_review_completion(self, response):
        user_submission = self.submission_for_user(response, self.user)
        self.assertEqual(user_submission.peer_reviews_completed, 1)
        self.assertEqual(user_submission.peer_reviews_total, 2)


class ProjectSubmissionsViewTestBase(
    ProjectSubmissionsFixtureMixin,
    ProjectSubmissionsRequestMixin,
    ProjectSubmissionsDataMixin,
    ProjectSubmissionsPeerReviewMixin,
    TestCase,
):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.admin_user = self.create_admin_user()
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.project = self.create_project()
        self.submission = self.create_initial_submission()


class ProjectSubmissionsAccessTests(ProjectSubmissionsViewTestBase):
    def test_submissions_view_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected"""
        submissions_url = self.project_submissions_url()
        response = self.client.get(submissions_url)

        # Should redirect to project view with error message
        self.assertEqual(response.status_code, 302)
        project_url = self.project_url()
        self.assertRedirects(response, project_url)

    def test_submissions_view_regular_user_denied(self):
        """Test that regular users cannot access submissions view"""
        self.client.login(**credentials)
        submissions_url = self.project_submissions_url()
        response = self.client.get(submissions_url)

        # Should redirect to project view with error message
        self.assertEqual(response.status_code, 302)
        project_url = self.project_url()
        self.assertRedirects(response, project_url)


class ProjectSubmissionsDisplayTests(ProjectSubmissionsViewTestBase):
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


class ProjectSubmissionsAdminLinkTests(ProjectSubmissionsViewTestBase):
    def test_admin_link_visible_to_staff(self):
        """Test that the admin link is visible to staff users"""
        self.login_admin()
        project_url = self.project_url()
        response = self.client.get(project_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Manage project in cadmin"
        )
        cadmin_submissions_url = self.cadmin_project_submissions_url()
        self.assertContains(response, cadmin_submissions_url)

    def test_admin_link_not_visible_to_regular_users(self):
        """Test that the admin link is not visible to regular users"""
        self.client.login(**credentials)
        project_url = self.project_url()
        response = self.client.get(project_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "Manage project in cadmin"
        )


class ProjectSubmissionsPeerReviewTests(ProjectSubmissionsViewTestBase):
    def test_peer_review_completion_displayed(self):
        """Test that peer review completion is displayed correctly"""
        self.create_peer_review_completion_fixture()

        response = self.admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assert_peer_review_completion(response)


class ProjectSubmissionsCopyEmailTests(ProjectSubmissionsViewTestBase):
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
        new_project = self.create_empty_project()

        response = self.admin_submissions_response(new_project)

        self.assertEqual(response.status_code, 200)
        # Check that the copy button is not present
        self.assertNotContains(response, 'id="copyEmailsBtn"')
