from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
)


class PeerReviewBadgeTests(TestCase):
    """Test cases for peer review badge color changes based on completion status"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="12345"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course
        )

        # Create a project in peer review state
        self.pr_project = Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
        )

    def test_peer_review_badge_red_when_not_completed(self):
        """Test that the badge is red when peer reviews are not completed"""
        # Create a submission with reviewed_enough_peers = False
        ProjectSubmission.objects.create(
            project=self.pr_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            reviewed_enough_peers=False
        )

        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be red (bg-danger) and state should be "Review"
        self.assertEqual(project.badge_css_class, "bg-danger")
        self.assertEqual(project.badge_state_name, "Review")

    def test_peer_review_badge_green_when_completed(self):
        """Test that the badge is green when peer reviews are completed"""
        # Create a submission with reviewed_enough_peers = True
        ProjectSubmission.objects.create(
            project=self.pr_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            reviewed_enough_peers=True
        )

        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be green (bg-success) and state should be "Review completed"
        self.assertEqual(project.badge_css_class, "bg-success")
        self.assertEqual(project.badge_state_name, "Review completed")

    def test_peer_review_badge_secondary_when_not_submitted(self):
        """Test that the badge is secondary (gray) when project is not submitted"""
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be secondary (bg-secondary) when not submitted
        self.assertEqual(project.badge_css_class, "bg-secondary")
        self.assertEqual(project.badge_state_name, "Not submitted")
