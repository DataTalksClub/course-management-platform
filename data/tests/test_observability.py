from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from course_management.observability import record_event
from course_management.observability.cloudwatch import (
    CloudWatchMetricsConfig,
    CloudWatchMetricsEventBackend,
    cloudwatch_metric_payload,
)
from course_management.observability.events import AppEvent
from course_management.middleware import ObservabilityExceptionMiddleware


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
            properties={
                "course_slug": "mlops",
                "event": "custom",
                "name": "unsafe-log-record-name",
            },
        )

        properties = event.normalized_properties()

        self.assertEqual(properties["event"], "homework.submitted")
        self.assertEqual(properties["schema_version"], "1")
        self.assertEqual(properties["environment"], "test")
        self.assertEqual(properties["release"], "test-release")
        self.assertEqual(properties["course_slug"], "mlops")
        self.assertEqual(properties["app_event"], "custom")
        self.assertEqual(
            properties["app_name"],
            "unsafe-log-record-name",
        )

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
        OBSERVABILITY_ENVIRONMENT="test",
        CLOUDWATCH_APP_METRIC_NAMESPACE="CMP/Test",
        VERSION="release-1",
    )
    def test_cloudwatch_metric_payload_uses_emf_schema(self):
        event = AppEvent(
            name="project.submitted",
            distinct_id="user:2",
            properties={"project_slug": "capstone"},
        )

        payload = cloudwatch_metric_payload(
            event,
            config=CloudWatchMetricsConfig(namespace="CMP/Test"),
        )

        self.assertEqual(payload["event"], "project.submitted")
        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["environment"], "test")
        self.assertEqual(payload["release"], "release-1")
        self.assertEqual(payload["project_slug"], "capstone")
        self.assertEqual(payload["distinct_id"], "user:2")
        self.assertEqual(payload["AppEventCount"], 1)
        self.assertIsInstance(payload["_aws"]["Timestamp"], int)
        metric = payload["_aws"]["CloudWatchMetrics"][0]
        self.assertEqual(metric["Namespace"], "CMP/Test")
        self.assertEqual(metric["Dimensions"], [["environment", "event"]])
        self.assertEqual(
            metric["Metrics"],
            [{"Name": "AppEventCount", "Unit": "Count"}],
        )

    @override_settings(CLOUDWATCH_APP_METRIC_NAMESPACE="CMP/Test")
    @patch("course_management.observability.cloudwatch.logger")
    def test_cloudwatch_backend_logs_metric_payload(self, logger_mock):
        event = AppEvent(name="registration.submitted", distinct_id="user:3")

        CloudWatchMetricsEventBackend().record(event)

        logger_mock.info.assert_called_once()
        args, kwargs = logger_mock.info.call_args
        self.assertEqual(args[0], "cloudwatch_app_event")
        extra = kwargs["extra"]
        self.assertEqual(extra["event"], "registration.submitted")
        self.assertEqual(extra["AppEventCount"], 1)
        self.assertEqual(
            extra["_aws"]["CloudWatchMetrics"][0]["Namespace"],
            "CMP/Test",
        )


class DatamailerMonitoringCommandTests(TestCase):
    @override_settings(
        OBSERVABILITY_EVENT_BACKENDS=["noop"],
    )
    def test_monitoring_datamailer_health_command_outputs_json(self):
        output = StringIO()

        call_command("monitoring_datamailer_health", "--json", stdout=output)

        self.assertIn('"status": "ok"', output.getvalue())
        self.assertIn('"outbox_due_count": 0', output.getvalue())

    @patch(
        "data.management.commands.monitoring_datamailer_health."
        "datamailer_health_payload",
        return_value={"status": "warning", "outbox_failed_count": 1},
    )
    @patch("data.management.commands.monitoring_datamailer_health.record_event")
    def test_monitoring_datamailer_health_emits_warning_event(
        self,
        record_event_mock,
        health_payload_mock,
    ):
        call_command("monitoring_datamailer_health", stdout=StringIO())

        health_payload_mock.assert_called_once_with()
        self.assertEqual(record_event_mock.call_count, 2)
        record_event_mock.assert_any_call(
            "datamailer.health_checked",
            properties={"status": "warning", "outbox_failed_count": 1},
        )
        record_event_mock.assert_any_call(
            "datamailer.health_warning",
            properties={"status": "warning", "outbox_failed_count": 1},
        )


class ObservabilityExceptionMiddlewareTests(SimpleTestCase):
    @patch("course_management.middleware.report_exception")
    def test_process_exception_reports_through_observability(
        self,
        report_exception_mock,
    ):
        request = RequestFactory().get("/broken")
        exception = ValueError("boom")
        middleware = ObservabilityExceptionMiddleware(lambda request: None)

        result = middleware.process_exception(request, exception)

        self.assertIsNone(result)
        report_exception_mock.assert_called_once_with(
            exception,
            request=request,
            properties={"source": "django.request"},
        )

    @patch("course_management.observability.events.logger")
    def test_report_exception_sanitizes_log_record_fields(self, logger_mock):
        from course_management.observability.events import report_exception

        exception = ValueError("boom")

        report_exception(exception, properties={"name": "unsafe"})

        self.assertEqual(
            logger_mock.exception.call_args.kwargs["extra"],
            {"app_name": "unsafe"},
        )
