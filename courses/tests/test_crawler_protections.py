"""Crawler protections: robots.txt, per-IP rate limiting, template fix, cache."""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from course_management.middleware import reset_rate_limit_state
from courses.models import Course, Enrollment, Homework, Project, ProjectState, User
from courses.views.course_list import ANON_HOMEPAGE_CACHE_KEY

logger = logging.getLogger(__name__)


@override_settings(RATELIMIT_ENABLED=True)
class RobotsTxtTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_robots_txt_served_with_leaderboard_disallow(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response["Content-Type"].startswith("text/plain")
        )
        body = response.content.decode()
        self.assertIn("Disallow: /*/leaderboard/", body)
        self.assertIn("Crawl-delay:", body)


@override_settings(
    RATELIMIT_ENABLED=True, RATELIMIT_AVERAGE=0, RATELIMIT_BURST=3
)
class RateLimitTestCase(TestCase):
    """Token bucket: 3 immediate requests, then 429; health exempt."""

    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test course description",
        )

    def setUp(self):
        reset_rate_limit_state()
        self.client = Client()
        self.course = self.create_course()
        credentials = {
            "username": "test@test.com",
            "email": "test@test.com",
            "password": "testpass123",
        }
        self.user = User.objects.create_user(**credentials)
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test User",
        )
        self.target = (
            f"/{self.course.slug}/leaderboard/{self.enrollment.id}/"
        )

    def tearDown(self):
        reset_rate_limit_state()

    def test_burst_then_429_on_score_breakdown(self):
        statuses = [
            self.client.get(self.target).status_code for _ in range(6)
        ]
        self.assertEqual(statuses[:3], [200, 200, 200])
        self.assertIn(429, statuses[3:])
        last_limited = None
        for _ in range(6):
            response = self.client.get(self.target)
            if response.status_code == 429:
                last_limited = response
        self.assertIsNotNone(last_limited)
        self.assertEqual(last_limited["Retry-After"], "1")

    def test_health_and_monitor_paths_exempt(self):
        statuses = [
            self.client.get(self.target).status_code for _ in range(6)
        ]
        self.assertIn(429, statuses)
        for _ in range(3):
            self.assertEqual(self.client.get(self.target).status_code, 429)
        for path in ["/api/health/", "/", "/ping", "/robots.txt"]:
            for _ in range(3):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_buckets_are_per_ip(self):
        for _ in range(6):
            self.client.get(
                self.target, HTTP_X_FORWARDED_FOR="203.0.113.7"
            )
        limited = self.client.get(
            self.target, HTTP_X_FORWARDED_FOR="203.0.113.7"
        )
        self.assertEqual(limited.status_code, 429)
        other_ip = self.client.get(
            self.target, HTTP_X_FORWARDED_FOR="203.0.113.8"
        )
        self.assertEqual(other_ip.status_code, 200)

    def test_spoofed_first_xff_entry_ignored(self):
        for _ in range(6):
            self.client.get(
                self.target,
                HTTP_X_FORWARDED_FOR="198.51.100.9, 203.0.113.7",
            )
        limited = self.client.get(
            self.target, HTTP_X_FORWARDED_FOR="203.0.113.7"
        )
        self.assertEqual(limited.status_code, 429)


class RateLimitDefaultsTestCase(TestCase):
    """Default settings allow normal traffic through."""

    def setUp(self):
        reset_rate_limit_state()
        self.client = Client()

    def tearDown(self):
        reset_rate_limit_state()

    @override_settings(RATELIMIT_ENABLED=True)
    def test_single_requests_pass_with_defaults(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)


class LeaderboardTemplateFixTestCase(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test course description",
        )

    def create_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() - timedelta(days=1),
            state="SC",
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COMPLETED.value,
        )

    def setUp(self):
        self.client = Client()
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.project = self.create_project()
        credentials = {
            "username": "test@test.com",
            "email": "test@test.com",
            "password": "testpass123",
        }
        self.user = User.objects.create_user(**credentials)
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test User",
        )

    def test_no_form_action_literal_for_scrapers(self):
        """Inline JS must not contain `form.action` (scraped as a link)."""
        url = f"/{self.course.slug}/leaderboard/{self.enrollment.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("form.action", body)
        self.assertIn("setAttribute('action'", body)


@override_settings(HOMEPAGE_ANON_CACHE_ENABLED=True)
class HomepageCacheTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        cache.delete(ANON_HOMEPAGE_CACHE_KEY)
        Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test course description",
        )

    def tearDown(self):
        cache.delete(ANON_HOMEPAGE_CACHE_KEY)

    def test_anonymous_homepage_cached_and_public(self):
        first = self.client.get("/")
        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(cache.get(ANON_HOMEPAGE_CACHE_KEY))
        self.assertIn("public, max-age=", first["Cache-Control"])
        second = self.client.get("/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.content, second.content)

    def test_authenticated_homepage_bypasses_cache(self):
        credentials = {
            "username": "auth@test.com",
            "email": "auth@test.com",
            "password": "testpass123",
        }
        user = User.objects.create_user(**credentials)
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertIsNone(cache.get(ANON_HOMEPAGE_CACHE_KEY))
