from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from course_management.observability import ping_check, record_event
from course_management.observability.events import AppEvent
from course_management.observability.posthog import PostHogEventBackend


class ObservabilityEventTests(SimpleTestCase):
    @override_settings(
        OBSERVABILITY_ENVIRONMENT="test",
        OBSERVABILITY_EVENT_SCHEMA_VERSION="1",
        VERSION="test-release",
    )
    def test_event_properties_use_project_schema(self):
        event = AppEvent(
            name="homework.submitted",
            distinct_id="user:1",
            properties={"course_slug": "mlops", "event": "custom"},
        )

        properties = event.normalized_properties()

        self.assertEqual(properties["event"], "homework.submitted")
        self.assertEqual(properties["schema_version"], "1")
        self.assertEqual(properties["environment"], "test")
        self.assertEqual(properties["release"], "test-release")
        self.assertEqual(properties["course_slug"], "mlops")
        self.assertEqual(properties["app_event"], "custom")

    @override_settings(OBSERVABILITY_EVENT_BACKENDS=["log"])
    def test_record_event_logs_without_external_keys(self):
        with self.assertLogs(
            "course_management.observability.events",
            level="INFO",
        ) as logs:
            record_event(
                "registration.submitted",
                distinct_id="user:10",
                properties={"course_slug": "de"},
            )

        self.assertIn("app_event", logs.output[0])

    @override_settings(
        POSTHOG_API_KEY="",
        POSTHOG_HOST="https://posthog.example",
    )
    @patch("course_management.observability.posthog.requests.post")
    def test_posthog_backend_is_noop_without_key(self, post_mock):
        event = AppEvent(name="project.submitted", distinct_id="user:1")

        PostHogEventBackend().record(event)

        post_mock.assert_not_called()

    @override_settings(
        POSTHOG_API_KEY="phc_test",
        POSTHOG_HOST="https://posthog.example",
        POSTHOG_TIMEOUT_SECONDS=3.0,
        POSTHOG_STRICT=True,
        OBSERVABILITY_ENVIRONMENT="test",
        VERSION="release-1",
    )
    @patch("course_management.observability.posthog.requests.post")
    def test_posthog_backend_sends_project_schema(self, post_mock):
        response = Mock()
        response.raise_for_status.return_value = None
        post_mock.return_value = response
        event = AppEvent(
            name="project.submitted",
            distinct_id="user:2",
            properties={"project_slug": "capstone"},
        )

        PostHogEventBackend().record(event)

        post_mock.assert_called_once()
        args, kwargs = post_mock.call_args
        self.assertEqual(args[0], "https://posthog.example/capture/")
        self.assertEqual(kwargs["timeout"], 3.0)
        self.assertEqual(kwargs["json"]["api_key"], "phc_test")
        self.assertEqual(kwargs["json"]["event"], "project.submitted")
        self.assertEqual(kwargs["json"]["distinct_id"], "user:2")
        properties = kwargs["json"]["properties"]
        self.assertEqual(properties["schema_version"], "1")
        self.assertEqual(properties["environment"], "test")
        self.assertEqual(properties["release"], "release-1")
        self.assertEqual(properties["project_slug"], "capstone")

    @override_settings(HEALTHCHECKS_TIMEOUT_SECONDS=4.0)
    @patch("course_management.observability.healthchecks.requests.post")
    def test_healthcheck_ping_status_suffixes(self, post_mock):
        ping_check(
            "https://hc-ping.com/check-id",
            status="start",
            message="starting",
        )
        ping_check("https://hc-ping.com/check-id", status="fail")
        ping_check("https://hc-ping.com/check-id")

        urls = [call.args[0] for call in post_mock.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://hc-ping.com/check-id/start",
                "https://hc-ping.com/check-id/fail",
                "https://hc-ping.com/check-id",
            ],
        )
        self.assertEqual(post_mock.call_args_list[0].kwargs["timeout"], 4.0)


class DatamailerMonitoringCommandTests(TestCase):
    @override_settings(
        OBSERVABILITY_EVENT_BACKENDS=["noop"],
        HEALTHCHECKS_DATAMAILER_HEALTH_URL="",
    )
    def test_monitoring_datamailer_health_command_outputs_json(self):
        output = StringIO()

        call_command("monitoring_datamailer_health", "--json", stdout=output)

        self.assertIn('"status": "ok"', output.getvalue())
        self.assertIn('"outbox_due_count": 0', output.getvalue())
