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
    Homework,
    HomeworkState,
)


logger = logging.getLogger(__name__)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class CadminViewTests(TestCase):
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

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def test_course_list_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected from course list"""
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_course_list_non_staff_denied(self):
        """Test that non-staff users cannot access course list"""
        self.client.login(username="test@test.com", password="12345")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_course_list_staff_allowed(self):
        """Test that staff users can access course list"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course Administration")

    def test_course_admin_staff_allowed(self):
        """Test that staff users can access course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Admin Panel")

    def test_homework_submissions_redirect_from_courses(self):
        """Test that homework submissions view redirects to cadmin"""
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_project_submissions_redirect_from_courses(self):
        """Test that project submissions view redirects to cadmin"""
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_homework_submissions_staff_allowed(self):
        """Test that staff users can view homework submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.homework.title)

    def test_cadmin_project_submissions_staff_allowed(self):
        """Test that staff users can view project submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

