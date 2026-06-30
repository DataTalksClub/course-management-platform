from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
    User,
)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)

admin_credentials = dict(
    username="admin@test.com",
    password="admin123",
)


class CourseCadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(**credentials)
        User.objects.create_user(
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

    def create_course(self, slug, title, *, finished=False):
        return Course.objects.create(
            slug=slug,
            title=title,
            description=f"{title} Description",
            finished=finished,
        )

    def assert_course_list_order(self, response, active_course, finished_course):
        courses = list(response.context["courses"])
        self.assertEqual(courses[:2], [active_course, self.course])
        self.assertEqual(courses[-1], finished_course)

    def assert_course_list_links(self, response):
        cadmin_course_url = reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )
        public_course_url = reverse(
            "course",
            kwargs={"course_slug": self.course.slug},
        )
        django_admin_url = f"/admin/courses/course/{self.course.id}/change/"
        datamailer_operations_url = reverse("cadmin_datamailer_operations")

        self.assertContains(response, cadmin_course_url)
        self.assertContains(response, public_course_url)
        self.assertContains(response, django_admin_url)
        self.assertContains(response, datamailer_operations_url)

    def create_course_work_items(self):
        Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )
        Project.objects.create(
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
        url = reverse("cadmin_course_list")

        self.client.login(**credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_course_list_staff_allowed(self):
        """Test that staff users can access course list"""
        finished_course = self.create_course(
            slug="finished-course",
            title="Finished Course",
            finished=True,
        )
        active_course = self.create_course(
            slug="active-course",
            title="Active Course",
        )
        url = reverse("cadmin_course_list")

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course admin")
        self.assertNotContains(response, 'aria-label="Breadcrumb"')
        self.assert_course_list_order(response, active_course, finished_course)
        self.assert_course_list_links(response)
        self.assertNotContains(response, "> Manage <")
        self.assertNotContains(response, "> View <")

    def test_course_admin_staff_allowed(self):
        """Test that staff users can access course admin page"""
        self.create_course_work_items()
        url = reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )
        public_course_url = reverse(
            "course",
            kwargs={"course_slug": self.course.slug},
        )
        django_admin_url = f"/admin/courses/course/{self.course.id}/change/"

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Course admin")
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "Course Admin")
        self.assertContains(response, public_course_url)
        self.assertContains(response, django_admin_url)
        self.assertContains(response, 'title="View public course page"')
        self.assertContains(response, 'title="Edit in Django Admin"')
        self.assertContains(response, "cadmin-actions-menu")
        self.assertNotContains(response, "Needs attention")
        self.assertNotContains(response, "Course Page")
        self.assertNotContains(response, "Dashboard")
