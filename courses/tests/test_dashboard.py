from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from courses.leaderboard import update_leaderboard
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

    @override_settings(PUBLIC_PAGE_CACHE_ENABLED=True)
    def test_dashboard_cache_uses_database_leaderboard_version(self):
        cache.clear()
        url = reverse("dashboard", args=[self.course.slug])

        first_response = self.client.get(url)
        first_course = first_response.context["course"]
        old_version = first_course.leaderboard_cache_version
        old_cache_key = f"dashboard:{first_course.id}:v{old_version}"
        self.assertIsNotNone(cache.get(old_cache_key))
        self.assertGreater(first_response.context["avg_total_score"], 0)

        update_leaderboard(first_course)

        second_response = self.client.get(url)
        second_course = second_response.context["course"]
        new_version = second_course.leaderboard_cache_version
        new_cache_key = f"dashboard:{second_course.id}:v{new_version}"

        self.assertEqual(new_version, old_version + 1)
        self.assertIsNotNone(cache.get(new_cache_key))
        self.assertEqual(second_response.context["avg_total_score"], 0)
