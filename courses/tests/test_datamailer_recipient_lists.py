from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from course_management.datamailer.keys import (
    course_enrolled_list_key,
    course_graduates_list_key,
    project_passed_list_key,
    registration_list_key,
)
from courses.tests.datamailer_recipient_lists_base import (
    BulkUpsertMemberExpectation,
    DATAMAILER_SETTINGS,
    DatamailerRecipientListCommandTestBase,
)


class DatamailerRecipientListCommandMixin:
    def run_recipient_list_command(self, *args):
        out = StringIO()
        call_command("sync_datamailer_recipient_lists", *args, stdout=out)
        return out


class DatamailerRecipientListBulkUpsertTest(
    DatamailerRecipientListCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_recipient_list_backfill_command_bulk_upserts_registrations(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        registration = self.create_registration()
        course = registration.course

        out = self.run_recipient_list_command(
            "registrations",
            "--course-slug",
            course.slug,
        )

        list_key = registration_list_key(registration)
        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=list_key,
            source_object_key=f"registration:{registration.pk}",
            list_type="registrants",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_recipient_list_backfill_command_bulk_upserts_enrollments(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        enrollment = self.create_enrolled_student()
        course = enrollment.course

        out = self.run_recipient_list_command(
            "enrollments",
            "--course-slug",
            course.slug,
        )

        list_key = course_enrolled_list_key(course)
        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=list_key,
            source_object_key=f"user:{enrollment.student_id}",
            list_type="custom",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)


class DatamailerRecipientListProjectPassedTest(
    DatamailerRecipientListCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.reconcile"
    )
    def test_recipient_list_backfill_command_reconciles_project_passed_outcomes(
        self,
        reconcile,
    ):
        self.configure_reconcile_success(reconcile)
        project, passed_submission = (
            self.create_passed_and_failed_project_submissions()
        )

        out = self.run_recipient_list_command(
            "project-passed",
            "--project-slug",
            project.slug,
            "--reconcile",
        )

        self.assert_project_passed_reconcile_call(
            reconcile,
            project,
            passed_submission,
        )
        self.assert_prepared_one_member(out)

    def configure_reconcile_success(self, reconcile):
        reconcile.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }

    def assert_project_passed_reconcile_call(
        self,
        reconcile,
        project,
        passed_submission,
    ):
        reconcile.assert_called_once()
        list_key = reconcile.call_args.args[0]
        expected_list_key = project_passed_list_key(project)
        self.assertEqual(list_key, expected_list_key)

        payload = reconcile.call_args.args[1]
        self.assertEqual(
            payload["list"]["metadata"]["outcome"],
            "project_passed",
        )
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{passed_submission.pk}",
        )


class DatamailerRecipientListGraduateTest(
    DatamailerRecipientListCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_recipient_list_backfill_command_bulk_upserts_graduates(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        course, enrollment = self.create_graduate_and_non_graduate()

        out = self.run_recipient_list_command(
            "graduates",
            "--course-slug",
            course.slug,
        )

        list_key = course_graduates_list_key(course)
        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=list_key,
            source_object_key=f"enrollment:{enrollment.pk}",
            outcome="course_graduated",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)


class DatamailerRecipientListDryRunTest(
    DatamailerRecipientListCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_recipient_list_backfill_command_dry_run_does_not_call_datamailer(
        self,
        bulk_upsert,
    ):
        self.create_registration()

        out = self.run_recipient_list_command(
            "registrations",
            "--dry-run",
        )

        bulk_upsert.assert_not_called()
        output = out.getvalue()
        self.assertIn(
            "ml-zoomcamp-2026: 1 member(s)",
            output,
        )


class DatamailerRecipientListOptionValidationTest(
    DatamailerRecipientListCommandTestBase
):
    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_backfill_command_rejects_invalid_options(self):
        for args, message in (
            (
                ("registrations", "--homework-slug", "homework-1"),
                "--homework-slug can only be used with kind=homework.",
            ),
            (
                ("enrollments", "--project-slug", "project-1"),
                "--project-slug can only be used with kind=project or kind=project-passed.",
            ),
            (
                ("registrations", "--wait-for-import"),
                "--wait-for-import requires --import-by-reference.",
            ),
            (
                ("registrations", "--import-timeout", "0"),
                "--import-timeout must be positive.",
            ),
            (
                ("registrations", "--import-poll-interval", "0"),
                "--import-poll-interval must be positive.",
            ),
        ):
            with self.subTest(args=args):
                with self.assertRaisesMessage(CommandError, message):
                    call_command("sync_datamailer_recipient_lists", *args)
