"""Regression coverage for GSC crawl policy and anonymous access."""

import re

from django.test import TestCase, override_settings

from courses.models import Course, Enrollment, User


def googlebot_allowed(body, path):
    """Match Google's wildcard/end-anchor and longest-rule semantics.

    urllib.robotparser does not implement Google's * and $ syntax.
    This fixture only needs the single User-agent: * group we serve.
    """
    matches = []
    for line in body.splitlines():
        directive, _, rule = line.partition(": ")
        if directive not in {"Allow", "Disallow"}:
            continue
        pattern = re.escape(rule).replace(r"\*", ".*")
        pattern = pattern.replace(r"\$", r"\Z")
        if re.match(pattern, path):
            matches.append(
                (len(rule.rstrip("$")), directive == "Allow")
            )
    return max(matches, default=(0, True))[1]


class GscCrawlerPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(
            slug="gsc-course", title="GSC"
        )
        user = User.objects.create_user(username="gsc-student")
        cls.enrollment = Enrollment.objects.create(
            course=cls.course,
            student=user,
        )

    def test_googlebot_leaderboard_policy(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Allow: /*/leaderboard$", body)
        self.assertIn("Crawl-delay: 10", body)
        for course in ("gsc-course", "ml-zoomcamp-2026"):
            base = f"/{course}/leaderboard"
            for suffix, allowed in (
                ("", True),
                ("?page=1", False),
                ("?page=4", False),
                ("?sort=score&page=2", False),
                ("/", False),
                ("/123/", False),
                ("/123/report", False),
            ):
                with self.subTest(path=base + suffix):
                    self.assertEqual(
                        googlebot_allowed(body, base + suffix),
                        allowed,
                    )
        for path in (
            "/accounts/login/",
            "/accounts/github/login/",
            "/accounts/settings/",
            "/api/courses/",
            "/admin/",
            "/cadmin/",
        ):
            with self.subTest(path=path):
                self.assertFalse(googlebot_allowed(body, path))
        self.assertTrue(googlebot_allowed(body, "/gsc-course/"))

    def test_anonymous_gated_paths_keep_status_and_are_noindex(self):
        for path, status in (
            ("/accounts/login/", 200),
            ("/accounts/settings/", 302),
            ("/accounts/email/", 403),
            ("/accounts/password/reset/", 403),
            ("/api/courses/", 401),
            ("/api/openapi.json", 401),
            ("/admin/", 302),
            ("/cadmin/", 302),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(
                    response.headers.get("X-Robots-Tag"), "noindex"
                )
        response = self.client.get("/accounts/login/")
        self.assertContains(
            response, '<meta name="robots" content="noindex">'
        )

    def test_public_pages_remain_anonymously_accessible(self):
        base = f"/{self.course.slug}"
        for path in (
            base + "/",
            base + "/leaderboard",
            base + "/leaderboard?page=4",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Robots-Tag", response.headers)
        breakdown = f"{base}/leaderboard/{self.enrollment.pk}/"
        response = self.client.get(breakdown)
        self.assertContains(
            response, '<meta name="robots" content="noindex">'
        )
        response = self.client.get(breakdown + "report")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        response = self.client.get(base + "/leaderboard/999999999/")
        self.assertEqual(response.status_code, 404)
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @override_settings(
        ALLOWED_HOSTS=[
            "localhost",
            "127.0.0.1",
            "dev.courses.datatalks.club",
            "courses.datatalks.club",
        ]
    )
    def test_dev_host_public_routes_are_noindex_while_prod_is_not(self):
        base = f"/{self.course.slug}"
        public_paths = (
            "/",
            base + "/",
            base + "/leaderboard",
            base + "/leaderboard?page=4",
        )

        # robots.txt must still allow crawling public dev routes so search
        # engines can fetch and observe the X-Robots-Tag: noindex directive.
        robots_resp = self.client.get(
            "/robots.txt", HTTP_HOST="dev.courses.datatalks.club"
        )
        self.assertEqual(robots_resp.status_code, 200)
        robots_body = robots_resp.content.decode()
        for path in ("/", base + "/", base + "/leaderboard"):
            with self.subTest(robots_allowed=path):
                self.assertTrue(googlebot_allowed(robots_body, path))

        # Dev host receives X-Robots-Tag: noindex on homepage and nested
        # public course routes, even if X-Forwarded-Host claims prod.
        for path in public_paths:
            with self.subTest(dev_path=path):
                response = self.client.get(
                    path,
                    HTTP_HOST="dev.courses.datatalks.club",
                    HTTP_X_FORWARDED_HOST="courses.datatalks.club",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.headers.get("X-Robots-Tag"), "noindex"
                )

        # Production host must NOT receive X-Robots-Tag: noindex on public
        # routes, even if X-Forwarded-Host is spoofed to the dev hostname.
        for path in public_paths:
            with self.subTest(prod_path=path):
                response = self.client.get(
                    path,
                    HTTP_HOST="courses.datatalks.club",
                    HTTP_X_FORWARDED_HOST="dev.courses.datatalks.club",
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Robots-Tag", response.headers)
