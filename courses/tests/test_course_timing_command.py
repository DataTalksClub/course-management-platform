import json
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class CourseTimingCommandTests(SimpleTestCase):
    @patch.dict("os.environ", {"TIMING_TEST_TOKEN": "test-token"})
    @patch("courses.management.commands.course_timing.requests.request")
    def test_authenticated_update_and_clear(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = {"starts_at": None}
        output = StringIO()
        call_command(
            "course_timing",
            "ml-2026",
            base_url="https://example.test",
            token_env="TIMING_TEST_TOKEN",
            homework="one",
            clear_start=True,
            due_date="2026-01-30T10:00:00Z",
            stdout=output,
        )
        args, kwargs = request.call_args
        self.assertEqual(
            args,
            (
                "PATCH",
                "https://example.test/api/courses/ml-2026/homeworks/by-slug/one/",
            ),
        )
        self.assertEqual(
            kwargs["headers"], {"Authorization": "Token test-token"}
        )
        self.assertEqual(
            kwargs["json"],
            {"starts_at": None, "due_date": "2026-01-30T10:00:00Z"},
        )
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(
            json.loads(output.getvalue()), {"starts_at": None}
        )

    @patch.dict("os.environ", {"TIMING_TEST_TOKEN": "test-token"})
    @patch("courses.management.commands.course_timing.requests.request")
    def test_read_and_auth_denial(self, request):
        request.return_value = Mock(status_code=403)
        with self.assertRaisesMessage(CommandError, "HTTP 403"):
            call_command(
                "course_timing",
                "ml",
                base_url="https://example.test",
                token_env="TIMING_TEST_TOKEN",
            )
        self.assertEqual(request.call_args.args[0], "GET")

    def test_insecure_remote_origin_rejected(self):
        with self.assertRaisesMessage(CommandError, "HTTPS"):
            call_command(
                "course_timing", "ml", base_url="http://example.test"
            )

    @patch.dict("os.environ", {"TIMING_TEST_TOKEN": "test-token"})
    @patch("courses.management.commands.course_timing.requests.request")
    def test_project_start_and_deadline_request(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = {
            "starts_at": "2026-01-01T00:00:00Z"
        }
        call_command(
            "course_timing",
            "ml",
            base_url="https://example.test",
            token_env="TIMING_TEST_TOKEN",
            project="final",
            starts_at="2026-01-01T00:00:00Z",
            submission_due_date="2026-01-10T00:00:00Z",
            stdout=StringIO(),
        )
        self.assertEqual(
            request.call_args.kwargs["json"],
            {
                "starts_at": "2026-01-01T00:00:00Z",
                "submission_due_date": "2026-01-10T00:00:00Z",
            },
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("courses.management.commands.course_timing.requests.request")
    def test_missing_token_never_requests(self, request):
        with self.assertRaisesMessage(
            CommandError, "token environment variable"
        ):
            call_command(
                "course_timing", "ml", base_url="https://example.test"
            )
        request.assert_not_called()
