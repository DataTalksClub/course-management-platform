from dataclasses import dataclass
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.keys import (
    course_enrolled_list_key,
    course_graduates_list_key,
    project_passed_list_key,
    registration_list_key,
)
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    Project,
    ProjectSubmission,
    RegistrationCampaign,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class BulkUpsertMemberExpectation:
    bulk_upsert: object
    list_key: str
    source_object_key: str
    list_type: str | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class ImportWaitExpectation:
    recipient_list_import: object
    course: Course
    job_id: int
    out: StringIO


class DatamailerRecipientListCommandTest(TestCase):
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_user(self, email):
        return CustomUser.objects.create_user(
            username=email,
            email=email,
            password="test",
        )

    def create_enrollment(self, user, course, **overrides):
        defaults = {"student": user, "course": course}
        defaults.update(overrides)
        return Enrollment.objects.create(**defaults)

    def create_registration(self, course=None, **overrides):
        course = course or self.create_ml_course()
        campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            current_course=course,
        )
        defaults = {
            "campaign": campaign,
            "course": course,
            "email": "Student@Example.com",
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "accepted_newsletter": True,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def create_project(self, course=None, **overrides):
        defaults = {
            "course": course or self.create_ml_course(),
            "slug": "project-1",
            "title": "Project 1",
            "submission_due_date": "2026-01-01T00:00:00Z",
            "peer_review_due_date": "2026-01-08T00:00:00Z",
        }
        defaults.update(overrides)
        return Project.objects.create(**defaults)

    def create_project_submission(self, project, user, **overrides):
        defaults = {
            "project": project,
            "student": user,
            "enrollment": self.create_enrollment(user, project.course),
            "github_link": "https://github.com/example/project",
            "commit_id": "abc123",
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def create_enrolled_student(self, course=None):
        course = course or self.create_ml_course()
        user = self.create_user("student@example.com")
        return self.create_enrollment(user, course)

    def create_graduate_and_non_graduate(self):
        course = self.create_ml_course()
        graduate = self.create_enrollment(
            self.create_user("student@example.com"),
            course,
        )
        graduate.total_score = 91
        graduate.certificate_url = "/certificates/student.pdf"
        graduate.save(update_fields=["total_score", "certificate_url"])
        Enrollment.objects.create(
            student=self.create_user("no-certificate@example.com"),
            course=course,
            certificate_url="",
        )
        return course, graduate

    def create_passed_and_failed_project_submissions(self):
        project = self.create_project()
        passed_submission = self.create_project_submission(
            project,
            self.create_user("passed@example.com"),
            github_link="https://github.com/example/passed",
            total_score=98,
            passed=True,
        )
        self.create_project_submission(
            project,
            self.create_user("failed@example.com"),
            github_link="https://github.com/example/failed",
            total_score=50,
            passed=False,
        )
        return project, passed_submission

    def configure_bulk_upsert_success(self, bulk_upsert):
        bulk_upsert.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }

    def assert_prepared_one_member(self, out):
        self.assertIn(
            "Prepared 1 recipient list(s), 1 member(s).", out.getvalue()
        )

    def assert_bulk_upsert_member(self, expectation):
        expectation.bulk_upsert.assert_called_once()
        self.assertEqual(
            expectation.bulk_upsert.call_args.args[0],
            expectation.list_key,
        )
        payload = expectation.bulk_upsert.call_args.args[1]
        if expectation.list_type is not None:
            self.assertEqual(payload["list"]["type"], expectation.list_type)
        if expectation.outcome is not None:
            self.assertEqual(
                payload["list"]["metadata"]["outcome"],
                expectation.outcome,
            )
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            expectation.source_object_key,
        )

    def configure_import_by_reference(self, boto3_client, create_import, job_id):
        s3 = boto3_client.return_value
        s3.generate_presigned_url.return_value = (
            "https://storage.example.com/import.jsonl?signature=abc"
        )
        create_import.return_value = {
            "import_job": {"id": job_id, "status": "pending"}
        }
        return s3

    def assert_registration_import_object(self, s3, registration):
        s3.put_object.assert_called_once()
        put_kwargs = s3.put_object.call_args.kwargs
        self.assertEqual(put_kwargs["Bucket"], "cmp-imports")
        self.assertTrue(
            put_kwargs["Key"].startswith(
                "datamailer-test/dtc-courses/dtc-courses/registrations/"
            )
        )
        self.assertEqual(
            put_kwargs["ContentType"],
            "application/x-ndjson",
        )
        rows = []
        body = put_kwargs["Body"].decode("utf-8")
        lines = body.splitlines()
        for line in lines:
            row = json.loads(line)
            rows.append(row)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["source_object_key"],
            f"registration:{registration.pk}",
        )
        self.assertEqual(rows[0]["email"], "student@example.com")
        return put_kwargs["Key"]

    def assert_presigned_import_url_created(self, s3, key):
        s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "cmp-imports", "Key": key},
            ExpiresIn=900,
            HttpMethod="GET",
        )

    def assert_registration_import_payload(self, create_import, registration):
        create_import.assert_called_once()
        self.assertEqual(
            create_import.call_args.args[0],
            registration_list_key(registration),
        )
        payload = create_import.call_args.args[1]
        self.assertEqual(
            payload["source_url"],
            "https://storage.example.com/import.jsonl?signature=abc",
        )
        self.assertEqual(payload["list"]["type"], "registrants")
        self.assertFalse(payload["remove_absent"])
        self.assertTrue(
            payload["idempotency_key"].startswith(
                "cmp-recipient-list-import:registrations:"
            )
        )
        self.assertNotIn("members", payload)

    def configure_successful_import_polling(
        self, recipient_list_import, job_id
    ):
        recipient_list_import.side_effect = [
            {"import_job": {"id": job_id, "status": "processing"}},
            {
                "import_job": {
                    "id": job_id,
                    "status": "succeeded",
                    "row_count": 1,
                    "created_count": 1,
                    "updated_count": 0,
                    "removed_count": 0,
                }
            },
        ]

    def assert_import_waited_for_success(self, expectation):
        self.assertEqual(expectation.recipient_list_import.call_count, 2)
        expectation.recipient_list_import.assert_called_with(
            course_enrolled_list_key(expectation.course),
            expectation.job_id,
        )
        self.assertIn(
            f"Import job succeeded for "
            f"{course_enrolled_list_key(expectation.course)}: "
            f"job_id={expectation.job_id}",
            expectation.out.getvalue(),
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_bulk_upserts_registrations(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        registration = self.create_registration()
        course = registration.course

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "registrations",
            "--course-slug",
            course.slug,
            stdout=out,
        )

        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=registration_list_key(registration),
            source_object_key=f"registration:{registration.pk}",
            list_type="registrants",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_bulk_upserts_enrollments(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        enrollment = self.create_enrolled_student()
        course = enrollment.course

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "enrollments",
            "--course-slug",
            course.slug,
            stdout=out,
        )

        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=course_enrolled_list_key(course),
            source_object_key=f"user:{enrollment.student_id}",
            list_type="custom",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.reconcile_recipient_list_members"
    )
    def test_recipient_list_backfill_command_reconciles_project_passed_outcomes(
        self,
        reconcile,
    ):
        reconcile.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }
        project, passed_submission = (
            self.create_passed_and_failed_project_submissions()
        )

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "project-passed",
            "--project-slug",
            project.slug,
            "--reconcile",
            stdout=out,
        )

        reconcile.assert_called_once()
        self.assertEqual(
            reconcile.call_args.args[0],
            project_passed_list_key(project),
        )
        payload = reconcile.call_args.args[1]
        self.assertEqual(payload["list"]["metadata"]["outcome"], "project_passed")
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            f"project-submission:{passed_submission.pk}",
        )
        self.assertIn(
            "Prepared 1 recipient list(s), 1 member(s).", out.getvalue()
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_bulk_upserts_graduates(
        self,
        bulk_upsert,
    ):
        self.configure_bulk_upsert_success(bulk_upsert)
        course, enrollment = self.create_graduate_and_non_graduate()

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "graduates",
            "--course-slug",
            course.slug,
            stdout=out,
        )

        expectation = BulkUpsertMemberExpectation(
            bulk_upsert=bulk_upsert,
            list_key=course_graduates_list_key(course),
            source_object_key=f"enrollment:{enrollment.pk}",
            outcome="course_graduated",
        )
        self.assert_bulk_upsert_member(expectation)
        self.assert_prepared_one_member(out)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_dry_run_does_not_call_datamailer(
        self,
        bulk_upsert,
    ):
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            current_course=course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
            email="Student@Example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "registrations",
            "--dry-run",
            stdout=out,
        )

        bulk_upsert.assert_not_called()
        self.assertIn(
            "ml-zoomcamp-2026: 1 member(s)",
            out.getvalue(),
        )

    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_backfill_command_rejects_invalid_options(self):
        cases = [
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
        ]

        for args, message in cases:
            with self.subTest(args=args):
                with self.assertRaisesMessage(CommandError, message):
                    call_command("sync_datamailer_recipient_lists", *args)

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
        "courses.management.commands.sync_datamailer_recipient_lists.boto3.client"
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
        call_command(
            "sync_datamailer_recipient_lists",
            "registrations",
            "--course-slug",
            course.slug,
            "--import-by-reference",
            stdout=out,
        )

        key = self.assert_registration_import_object(s3, registration)
        self.assert_presigned_import_url_created(s3, key)
        self.assert_registration_import_payload(create_import, registration)
        self.assertIn(
            "Created import job for ml-zoomcamp-2026: job_id=17",
            out.getvalue(),
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
        "courses.management.commands.sync_datamailer_recipient_lists.boto3.client"
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

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "enrollments",
            "--course-slug",
            enrollment.course.slug,
            "--import-by-reference",
            "--wait-for-import",
            "--import-poll-interval",
            "0.01",
            stdout=out,
        )

        expectation = ImportWaitExpectation(
            recipient_list_import=recipient_list_import,
            course=enrollment.course,
            job_id=18,
            out=out,
        )
        self.assert_import_waited_for_success(expectation)

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
        "courses.management.commands.sync_datamailer_recipient_lists.boto3.client"
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
        recipient_list_import.return_value = {
            "import_job": {
                "id": 19,
                "status": "failed",
                "error": "bad jsonl",
            }
        }
        enrollment = self.create_enrolled_student()

        with self.assertRaisesMessage(
            CommandError,
            "Datamailer import job failed for "
            f"{course_enrolled_list_key(enrollment.course)}: "
            "job_id=19; error=bad jsonl",
        ):
            call_command(
                "sync_datamailer_recipient_lists",
                "enrollments",
                "--course-slug",
                enrollment.course.slug,
                "--import-by-reference",
                "--wait-for-import",
                stdout=StringIO(),
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
        "courses.management.commands.sync_datamailer_recipient_lists.boto3.client"
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
        recipient_list_import.return_value = {
            "import_job": {"id": 20, "status": "processing"}
        }
        enrollment = self.create_enrolled_student()

        with patch(
            "courses.management.commands.sync_datamailer_recipient_lists.time.monotonic",
            side_effect=[0, 2],
        ):
            with self.assertRaisesMessage(
                CommandError,
                "Timed out waiting for Datamailer import job "
                f"20 for {course_enrolled_list_key(enrollment.course)}; "
                "last status=processing",
            ):
                call_command(
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
                    stdout=StringIO(),
                )

    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_import_by_reference_requires_s3_bucket(self):
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            current_course=course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
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
