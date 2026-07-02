from django.urls import reverse

from courses.tests.dashboard_view_base import DashboardViewTestBase


class DashboardViewTestCase(DashboardViewTestBase):
    def test_dashboard_url_exists(self):
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_uses_correct_template(self):
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "courses/dashboard.html")

    def test_dashboard_context_basic(self):
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertIn("course", response.context)
        self.assertIn("total_enrollments", response.context)
        self.assertIn("homework_stats", response.context)
        self.assertIn("homework_difficulty_stats", response.context)
        self.assertIn("project_passing_score", response.context)

        self.assertEqual(response.context["course"], self.course)
        self.assertEqual(response.context["total_enrollments"], 6)
        self.assertEqual(response.context["project_passing_score"], 70)
