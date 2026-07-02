from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course

User = get_user_model()

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class DashboardAuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )

    def dashboard_url(self):
        return reverse("dashboard", args=[self.course.slug])

    def test_dashboard_access_without_login(self):
        dashboard_url = self.dashboard_url()
        response = self.client.get(dashboard_url)

        self.assertEqual(response.status_code, 200)

    def test_dashboard_access_with_login(self):
        User.objects.create_user(**credentials)
        self.client.login(**credentials)

        dashboard_url = self.dashboard_url()
        response = self.client.get(dashboard_url)

        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirects_before_first_homework_is_scored(self):
        self.course.first_homework_scored = False
        self.course.save()

        dashboard_url = self.dashboard_url()
        response = self.client.get(dashboard_url)
        course_url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        self.assertRedirects(response, course_url)
