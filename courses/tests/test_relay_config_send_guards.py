from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from course_management.datamailer.sync.notifications import (
    send_registration_confirmation_email,
)
from course_management.datamailer.sync.certificates import (
    send_certificate_availability_notification,
)
from course_management.datamailer.sync.score_notifications import (
    send_homework_score_notification,
    send_project_score_notification,
)
from course_management.datamailer.sync.peer_review_notifications import (
    send_peer_review_assignment_notification,
)
from course_management.datamailer.sync.transactional import (
    send_transactional_email,
)
from courses.tests.datamailer_contact_base import RELAY_SETTINGS
from data.models import DatamailerSendAudit, DatamailerSendAuditStatus


@override_settings(**RELAY_SETTINGS, RELAY_STRICT=False)
class RelayConfigSendGuardTests(TestCase):
    def test_notification_entry_points_audit_bad_config(self):
        senders = (
            send_registration_confirmation_email,
            send_certificate_availability_notification,
            send_homework_score_notification,
            send_project_score_notification,
            send_peer_review_assignment_notification,
        )
        for settings_override, reason in (
            ({"RELAY_API_KEY": ""}, "relay_config_missing"),
            ({"RELAY_URL": ""}, "relay_config_missing"),
            ({"RELAY_URL": "invalid"}, "relay_config_invalid"),
            ({"RELAY_URL": "https://[broken"}, "relay_config_invalid"),
        ):
            for sender in senders:
                with self.subTest(
                    sender=sender.__name__, settings=settings_override
                ):
                    DatamailerSendAudit.objects.all().delete()
                    with (
                        override_settings(**settings_override),
                        patch(
                            "course_management.datamailer.sync.transactional.record_event"
                        ) as events,
                    ):
                        sender(SimpleNamespace(pk=42))
                    audit = DatamailerSendAudit.objects.get()
                    self.assertEqual(
                        audit.status, DatamailerSendAuditStatus.FAILED
                    )
                    self.assertEqual(audit.error, reason)
                    self.assertTrue(audit.template_key)
                    self.assertTrue(
                        any(
                            call.args[0] == "datamailer.health_warning"
                            for call in events.call_args_list
                        )
                    )

    @patch(
        "course_management.datamailer.client.DatamailerConfig.from_settings",
        return_value=None,
    )
    def test_factory_returning_none_audits_even_without_idempotency_key(
        self, factory
    ):
        send_transactional_email({"template_key": "test"})
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertEqual(audit.error, "relay_config_missing")

    @override_settings(
        OBSERVABILITY_ENVIRONMENT="staging",
        RELAY_TRANSACTIONAL_DRY_RUN=True,
    )
    def test_historical_production_release_environment_reports_dry_run(
        self,
    ):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["RELAY_TRANSACTIONAL_DRY_RUN"], "FAIL"
        )
        from data.management.commands.monitoring_datamailer_health import (
            datamailer_health_payload,
        )

        self.assertEqual(datamailer_health_payload()["status"], "FAIL")
