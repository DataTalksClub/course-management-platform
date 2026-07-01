"""Tests for deliberate HTTP method handling on data endpoints."""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Course, Homework, Project, Enrollment


class DataEndpointMethodRestrictionTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_client = Client(
            HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
        )
        Enrollment.objects.create(student=self.user, course=self.course)
        now = timezone.now()
        self.homework = Homework.objects.create(
            course=self.course,
            title="Test Homework",
            slug="test-homework",
            due_date=now + timezone.timedelta(days=7),
        )
        self.project = Project.objects.create(
            course=self.course,
            title="Test Project",
            slug="test-project",
            submission_due_date=now + timezone.timedelta(days=7),
            peer_review_due_date=now + timezone.timedelta(days=14),
        )

    def get_only_routes(self):
        return [
            reverse("api_health"),
            reverse(
                "api_course_criteria_yaml",
                kwargs={"course_slug": self.course.slug},
            ),
            reverse(
                "api_course_leaderboard",
                kwargs={"course_slug": self.course.slug},
            ),
            reverse(
                "api_course_graduates",
                kwargs={"course_slug": self.course.slug},
            ),
            reverse(
                "api_homework_submissions_export",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
            reverse(
                "api_project_submissions_export",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
        ]

    def post_only_routes(self):
        return [
            reverse(
                "api_course_certificates",
                kwargs={"course_slug": self.course.slug},
            ),
            reverse("api_datamailer_events"),
        ]

    def assert_method_rejected(self, method, url, allowed_method):
        response = method(url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], allowed_method)

    def test_get_only_data_endpoints_reject_delete(self):
        routes = self.get_only_routes()

        for url in routes:
            with self.subTest(url=url):
                self.assert_method_rejected(
                    self.auth_client.delete,
                    url,
                    "GET",
                )

    def test_post_only_data_endpoints_reject_get(self):
        routes = self.post_only_routes()

        for url in routes:
            with self.subTest(url=url):
                self.assert_method_rejected(
                    self.auth_client.get,
                    url,
                    "POST",
                )
