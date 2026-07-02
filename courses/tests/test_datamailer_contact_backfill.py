from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings

from accounts.models import CustomUser
from courses.tests.datamailer_contact_base import (
    DATAMAILER_SETTINGS,
    DatamailerContactBase,
)


class DatamailerContactBackfillTest(DatamailerContactBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_bulk_imports_users(
        self,
        bulk_import,
    ):
        self.configure_contact_bulk_import_counts(bulk_import)
        self.create_contact_backfill_users()

        out = StringIO()
        call_command(
            "sync_datamailer_contacts",
            "--batch-size",
            "1",
            stdout=out,
        )

        self.assert_first_contact_import_payload(bulk_import)
        self.assert_contact_import_output(out)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_dry_run_does_not_call_datamailer(
        self,
        bulk_import,
    ):
        CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )

        out = StringIO()
        call_command("sync_datamailer_contacts", "--dry-run", stdout=out)

        bulk_import.assert_not_called()
        output = out.getvalue()
        self.assertIn("Prepared 1 contact batch(es), 1 contact(s).", output)
        self.assertIn("batch 1: 1 contact(s)", output)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_can_limit_to_active_users(
        self,
        bulk_import,
    ):
        bulk_import.return_value = {"counts": {"created": 1}}
        CustomUser.objects.create_user(
            username="active",
            email="active@example.com",
        )
        CustomUser.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            is_active=False,
        )

        out = StringIO()
        call_command("sync_datamailer_contacts", "--active-only", stdout=out)

        bulk_import.assert_called_once()
        payload = bulk_import.call_args.args[0]
        contacts_count = len(payload["contacts"])
        self.assertEqual(contacts_count, 1)
        self.assertEqual(payload["contacts"][0]["email"], "active@example.com")
