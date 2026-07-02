from urllib.parse import urlparse

from django.test import SimpleTestCase, override_settings

from course_management.datamailer.client import public_url


class PublicUrlTest(SimpleTestCase):
    @override_settings(PUBLIC_BASE_URL="https://courses.datatalks.club")
    def test_uses_public_base_url_when_configured(self):
        self.assertEqual(
            public_url("/llm-zoomcamp-2026/leaderboard"),
            "https://courses.datatalks.club/llm-zoomcamp-2026/leaderboard",
        )

    @override_settings(
        PUBLIC_BASE_URL="",
        ALLOWED_HOSTS=["courses.datatalks.club"],
    )
    def test_falls_back_to_host_when_base_url_missing(self):
        url = public_url("/llm-zoomcamp-2026/leaderboard")

        # Emails must never contain a hostless link like
        # http:///llm-zoomcamp-2026/leaderboard or a bare /path.
        self.assertTrue(urlparse(url).netloc, f"hostless URL: {url!r}")
        self.assertEqual(
            url,
            "https://courses.datatalks.club/llm-zoomcamp-2026/leaderboard",
        )

    @override_settings(
        PUBLIC_BASE_URL="http://",
        ALLOWED_HOSTS=["courses.datatalks.club"],
    )
    def test_falls_back_when_base_url_has_no_host(self):
        url = public_url("/llm-zoomcamp-2026/leaderboard")

        self.assertFalse(
            url.startswith("http:///"), f"hostless URL: {url!r}"
        )
        self.assertTrue(urlparse(url).netloc, f"hostless URL: {url!r}")
