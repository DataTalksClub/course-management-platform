from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from course_management.datamailer.keys import course_enrolled_list_key
from courses.tests.datamailer_recipient_lists_base import (
    DATAMAILER_SETTINGS,
    DatamailerRecipientListCommandTestBase,
    ImportWaitExpectation,
)


class DatamailerEnrollmentImportCommandMixin:
    def run_enrollment_import_by_reference(self, enrollment, *extra_args):
        out = StringIO()
        command_args = [
            "sync_datamailer_recipient_lists",
            "enrollments",
            "--course-slug",
            enrollment.course.slug,
            "--import-by-reference",
        ]
        command_args.extend(extra_args)
        call_command(
            *command_args,
            stdout=out,
        )
        return out


class DatamailerRecipientListImportCreationTest(
    DatamailerRecipientListCommandTestBase
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_IMPORT_S3_BUCKET="cmp-imports",
        DATAMAILER_IMPORT_S3_PREFIX="datamailer-test",
        DATAMAILER_IMPORT_URL_EXPIRES_SECONDS=900,
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.create_recipient_list_import"
    )
    @patch(
        "course_management.datamailer.recipient_list_imports.boto3.client"
    )
    def test_recipient_list_backfill_command_creates_import_job(
        self,
        boto3_client,
        create_import,
    ):
        s3 = self.configure_import_by_reference(
            boto3_client, create_import, job_id=17
        )
        registration = self.create_registration(accepted_newsletter=False)
        course = registration.course

        out = StringIO()
        command_args = [
            "sync_datamailer_recipient_lists",
            "registrations",
            "--course-slug",
            course.slug,
            "--import-by-reference",
        ]
        call_command(
            *command_args,
            stdout=out,
        )

        key = self.assert_registration_import_object(s3, registration)
        self.assert_presigned_import_url_created(s3, key)
        self.assert_registration_import_payload(create_import, registration)
        command_output = out.getvalue()
        self.assertIn(
            "Created import job for ml-zoomcamp-2026: job_id=17",
            command_output,
        )


class DatamailerRecipientListImportSuccessTest(
    DatamailerEnrollmentImportCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_IMPORT_S3_BUCKET="cmp-imports",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_import"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.create_recipient_list_import"
    )
    @patch(
        "course_management.datamailer.recipient_list_imports.boto3.client"
    )
    def test_recipient_list_backfill_command_waits_for_import_success(
        self,
        boto3_client,
        create_import,
        recipient_list_import,
    ):
        self.configure_import_by_reference(
            boto3_client, create_import, job_id=18
        )
        self.configure_successful_import_polling(
            recipient_list_import, job_id=18
        )
        enrollment = self.create_enrolled_student()

        out = self.run_enrollment_import_by_reference(
            enrollment,
            "--wait-for-import",
            "--import-poll-interval",
            "0.01",
        )

        expectation = ImportWaitExpectation(
            recipient_list_import=recipient_list_import,
            course=enrollment.course,
            job_id=18,
            out=out,
        )
        self.assert_import_waited_for_success(expectation)


class DatamailerRecipientListImportFailureTest(
    DatamailerEnrollmentImportCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_IMPORT_S3_BUCKET="cmp-imports",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_import"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.create_recipient_list_import"
    )
    @patch(
        "course_management.datamailer.recipient_list_imports.boto3.client"
    )
    def test_recipient_list_backfill_command_reports_import_failure(
        self,
        boto3_client,
        create_import,
        recipient_list_import,
    ):
        self.configure_import_by_reference(
            boto3_client, create_import, job_id=19
        )
        recipient_list_import.return_value = self.failed_import_response()
        enrollment = self.create_enrolled_student()

        with self.assertRaisesMessage(
            CommandError,
            "Datamailer import job failed for "
            f"{course_enrolled_list_key(enrollment.course)}: "
            "job_id=19; error=bad jsonl",
        ):
            self.run_enrollment_import_by_reference(
                enrollment,
                "--wait-for-import",
            )

    def failed_import_response(self):
        import_job = {
            "id": 19,
            "status": "failed",
            "error": "bad jsonl",
        }
        return {"import_job": import_job}


class DatamailerRecipientListImportTimeoutTest(
    DatamailerEnrollmentImportCommandMixin,
    DatamailerRecipientListCommandTestBase,
):
    def configure_processing_import_job(self, recipient_list_import, job_id):
        recipient_list_import.return_value = {
            "import_job": {"id": job_id, "status": "processing"}
        }

    def assert_import_wait_times_out(self, enrollment, job_id):
        message = (
            "Timed out waiting for Datamailer import job "
            f"{job_id} for {course_enrolled_list_key(enrollment.course)}; "
            "last status=processing"
        )
        with patch(
            "course_management.datamailer.recipient_list_import_jobs.time.monotonic",
            side_effect=[0, 2],
        ):
            with self.assertRaisesMessage(CommandError, message):
                stdout = StringIO()
                command_args = [
                    "sync_datamailer_recipient_lists",
                    "enrollments",
                    "--course-slug",
                    enrollment.course.slug,
                    "--import-by-reference",
                    "--wait-for-import",
                    "--import-timeout",
                    "1",
                    "--import-poll-interval",
                    "0.01",
                ]
                call_command(
                    *command_args,
                    stdout=stdout,
                )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_IMPORT_S3_BUCKET="cmp-imports",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_import"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.create_recipient_list_import"
    )
    @patch(
        "course_management.datamailer.recipient_list_imports.boto3.client"
    )
    def test_recipient_list_backfill_command_times_out_waiting_for_import(
        self,
        boto3_client,
        create_import,
        recipient_list_import,
    ):
        self.configure_import_by_reference(
            boto3_client, create_import, job_id=20
        )
        self.configure_processing_import_job(recipient_list_import, 20)
        enrollment = self.create_enrolled_student()

        self.assert_import_wait_times_out(enrollment, 20)


class DatamailerRecipientListImportValidationTest(
    DatamailerRecipientListCommandTestBase
):
    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_import_by_reference_requires_s3_bucket(self):
        self.create_registration(
            email="student@example.com",
            name="Student One",
        )

        with self.assertRaisesMessage(
            CommandError,
            "DATAMAILER_IMPORT_S3_BUCKET must be set",
        ):
            call_command(
                "sync_datamailer_recipient_lists",
                "registrations",
                "--import-by-reference",
            )
