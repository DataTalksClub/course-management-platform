from django.urls import reverse

from courses.models import Course
from courses.tests.dashboard_view_base import DashboardViewTestBase


class DashboardEmptyStateTestCase(DashboardViewTestBase):
    def test_dashboard_with_invalid_course(self):
        url = reverse("dashboard", args=["non-existent-course"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_dashboard_with_no_enrollments(self):
        empty_course = Course.objects.create(
            slug="empty-course",
            title="Empty Course",
            first_homework_scored=True,
        )

        url = reverse("dashboard", args=[empty_course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_enrollments"], 0)
