"""Tests for noindex meta tag on thin pages."""
import logging
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    Course,
    Homework,
    Project,
    ProjectState,
    User,
    Enrollment,
    ProjectSubmission,
)

logger = logging.getLogger(__name__)


class NoIndexMetaTagTestCase(TestCase):
    """Test that noindex meta tag is present on thin pages."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create a course
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test course description",
        )
        
        # Create a homework
        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() - timedelta(days=1),
            state="SC",  # SCORED state
        )
        
        # Create a project
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COMPLETED.value,
        )
        
        # Create a user and enrollment
        self.credentials = {
            "username": "test@test.com",
            "email": "test@test.com",
            "password": "testpass123"
        }
        self.user = User.objects.create_user(**self.credentials)
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test User"
        )
        
        # Create a project submission
        self.project_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/test",
            commit_id="abc123",
        )

    def test_leaderboard_score_breakdown_has_noindex(self):
        """Test that leaderboard score breakdown page has noindex meta tag."""
        url = f"/{self.course.slug}/leaderboard/{self.enrollment.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_project_list_has_noindex(self):
        """Test that project list page has noindex meta tag."""
        url = f"/{self.course.slug}/project/{self.project.slug}/list"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_project_eval_has_noindex(self):
        """Test that project evaluation page has noindex meta tag."""
        self.client.login(
            username=self.credentials["username"],
            password=self.credentials["password"]
        )
        url = f"/{self.course.slug}/project/{self.project.slug}/eval"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_project_results_has_noindex(self):
        """Test that project results page has noindex meta tag."""
        self.client.login(
            username=self.credentials["username"],
            password=self.credentials["password"]
        )
        url = f"/{self.course.slug}/project/{self.project.slug}/results"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_project_stats_has_noindex(self):
        """Test that project statistics page has noindex meta tag."""
        url = f"/{self.course.slug}/project/{self.project.slug}/stats"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_projects_list_all_has_noindex(self):
        """Test that all projects submissions page has noindex meta tag."""
        url = f"/{self.course.slug}/projects"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_enrollment_has_noindex(self):
        """Test that enrollment/profile editing page has noindex meta tag."""
        # Must be logged in to access enrollment page
        self.client.login(
            username=self.credentials["username"],
            password=self.credentials["password"]
        )
        url = f"/{self.course.slug}/enrollment"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_homework_stats_has_noindex(self):
        """Test that homework statistics page has noindex meta tag."""
        url = f"/{self.course.slug}/homework/{self.homework.slug}/stats"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex">')

    def test_course_page_does_not_have_noindex(self):
        """Test that main course page does NOT have noindex meta tag."""
        url = f"/{self.course.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<meta name="robots" content="noindex">')

    def test_course_list_does_not_have_noindex(self):
        """Test that course list page does NOT have noindex meta tag."""
        url = "/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<meta name="robots" content="noindex">')
