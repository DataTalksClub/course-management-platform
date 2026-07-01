from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectStatistics,
    ProjectSubmission,
    User,
)

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectStatisticsViewTestCase(TestCase):
    def create_admin_user(self):
        return User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

    def create_completed_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

    def create_incomplete_project(self):
        return Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def setUp(self):
        self.client = Client()
        self.admin_user = self.create_admin_user()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.project = self.create_completed_project()
        self.incomplete_project = self.create_incomplete_project()

    def create_project_statistics_submission(self):
        enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            total_score=20,
            time_spent=10.0,
        )

    def mock_project_statistics(self, mock_calc):
        mock_stats = ProjectStatistics(
            project=self.project,
            total_submissions=1,
            min_project_score=10,
            max_project_score=10,
            avg_project_score=10.0,
        )
        mock_calc.return_value = mock_stats
        return mock_stats

    def project_statistics_url(self, project=None):
        return reverse(
            "project_statistics",
            args=[self.course.slug, (project or self.project).slug],
        )

    def test_project_statistics_view_success(self):
        """Test successful project statistics view"""
        self.create_project_statistics_submission()

        with patch(
            "courses.views.project_statistics.calculate_project_statistics"
        ) as mock_calc:
            self.mock_project_statistics(mock_calc)
            response = self.client.get(self.project_statistics_url())

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Test Project statistics")
            self.assertContains(response, "Total submissions")
            self.assertIn("stats", response.context)
            self.assertEqual(response.context["project"], self.project)
            self.assertEqual(response.context["course"], self.course)

    def test_project_statistics_view_incomplete_project(self):
        """Test project statistics view redirects for incomplete project"""
        url = self.project_statistics_url(self.incomplete_project)
        response = self.client.get(url, follow=True)

        self.assertRedirects(
            response,
            reverse(
                "project",
                args=[self.course.slug, self.incomplete_project.slug],
            ),
        )

        messages = list(response.context["messages"])
        has_incomplete_project_message = False
        for message in messages:
            if "not completed yet" in str(message):
                has_incomplete_project_message = True
                break
        self.assertTrue(has_incomplete_project_message)

    def test_project_statistics_view_nonexistent_project(self):
        """Test project statistics view with non-existent project"""
        url = reverse(
            "project_statistics", args=[self.course.slug, "nonexistent"]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_project_statistics_view_nonexistent_course(self):
        """Test project statistics view with non-existent course"""
        url = reverse(
            "project_statistics",
            args=["nonexistent", self.project.slug],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_project_statistics_template_rendering(self):
        """Test that the template renders correctly"""
        self.create_project_statistics_submission()

        with patch(
            "courses.views.project_statistics.calculate_project_statistics"
        ) as mock_calc:
            self.mock_project_statistics(mock_calc)
            response = self.client.get(self.project_statistics_url())

            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "projects/stats.html")
            self.assertContains(response, "Test Project statistics")
            self.assertContains(response, "Total submissions")
