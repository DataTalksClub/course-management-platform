from django.test import RequestFactory, SimpleTestCase, override_settings

from courses.views.url_utils import absolute_url_with_fallback


class AbsoluteUrlWithFallbackTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(PUBLIC_BASE_URL="https://courses.example.com/base")
    def test_prefers_public_base_url(self):
        request = self.factory.get("/", HTTP_HOST="localhost")

        result = absolute_url_with_fallback(
            request,
            "/course/homework/hw1",
            label="homework",
        )

        self.assertEqual(
            result,
            "https://courses.example.com/base/course/homework/hw1",
        )

    @override_settings(PUBLIC_BASE_URL="", ALLOWED_HOSTS=["testserver"])
    def test_uses_request_host_when_allowed(self):
        request = self.factory.get(
            "/",
            HTTP_HOST="testserver",
            secure=True,
        )

        result = absolute_url_with_fallback(
            request,
            "/course/project/proj1",
            label="project",
        )

        self.assertEqual(result, "https://testserver/course/project/proj1")

    @override_settings(
        PUBLIC_BASE_URL="",
        ALLOWED_HOSTS=["allowed.example.com"],
    )
    def test_falls_back_to_allowed_host_when_request_host_is_rejected(self):
        request = self.factory.get("/", HTTP_HOST="bad.example.com")

        with self.assertLogs("courses.views.url_utils", level="WARNING") as logs:
            result = absolute_url_with_fallback(
                request,
                "/course/homework/hw1",
                label="homework",
            )

        self.assertEqual(
            result,
            "http://allowed.example.com/course/homework/hw1",
        )
        self.assertIn("homework update URL", logs.output[0])
