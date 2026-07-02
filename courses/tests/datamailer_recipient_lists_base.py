from dataclasses import dataclass
from io import StringIO
import json

from django.test import TestCase

from accounts.models import CustomUser
from course_management.datamailer.keys import (
    course_enrolled_list_key,
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


class DatamailerRecipientListFixtureMixin:
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
        enrollment = self.create_enrollment(user, project.course)
        defaults = {
            "project": project,
            "student": user,
            "enrollment": enrollment,
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
        student = self.create_user("student@example.com")
        graduate = self.create_enrollment(student, course)
        graduate.total_score = 91
        graduate.certificate_url = "/certificates/student.pdf"
        graduate.save(update_fields=["total_score", "certificate_url"])
        non_graduate = self.create_user("no-certificate@example.com")
        Enrollment.objects.create(
            student=non_graduate,
            course=course,
            certificate_url="",
        )
        return course, graduate

    def create_passed_and_failed_project_submissions(self):
        project = self.create_project()
        passed_user = self.create_user("passed@example.com")
        passed_submission = self.create_project_submission(
            project,
            passed_user,
            github_link="https://github.com/example/passed",
            total_score=98,
            passed=True,
        )
        failed_user = self.create_user("failed@example.com")
        self.create_project_submission(
            project,
            failed_user,
            github_link="https://github.com/example/failed",
            total_score=50,
            passed=False,
        )
        return project, passed_submission


class DatamailerRecipientListBulkUpsertMixin:
    def configure_bulk_upsert_success(self, bulk_upsert):
        bulk_upsert.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }

    def assert_prepared_one_member(self, out):
        output = out.getvalue()
        self.assertIn(
            "Prepared 1 recipient list(s), 1 member(s).", output
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


class DatamailerRecipientListImportSetupMixin:
    def configure_import_by_reference(self, boto3_client, create_import, job_id):
        s3 = boto3_client.return_value
        s3.generate_presigned_url.return_value = (
            "https://storage.example.com/import.jsonl?signature=abc"
        )
        create_import.return_value = {
            "import_job": {"id": job_id, "status": "pending"}
        }
        return s3


class DatamailerRegistrationImportAssertionsMixin:
    def assert_registration_import_object(self, s3, registration):
        s3.put_object.assert_called_once()
        put_kwargs = s3.put_object.call_args.kwargs
        self.assertEqual(put_kwargs["Bucket"], "cmp-imports")
        key_has_expected_prefix = put_kwargs["Key"].startswith(
            "datamailer-test/dtc-courses/dtc-courses/registrations/"
        )
        self.assertTrue(key_has_expected_prefix)
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
        from course_management.datamailer.keys import registration_list_key

        create_import.assert_called_once()
        expected_list_key = registration_list_key(registration)
        self.assertEqual(
            create_import.call_args.args[0],
            expected_list_key,
        )
        payload = create_import.call_args.args[1]
        self.assertEqual(
            payload["source_url"],
            "https://storage.example.com/import.jsonl?signature=abc",
        )
        self.assertEqual(payload["list"]["type"], "registrants")
        self.assertFalse(payload["remove_absent"])
        has_expected_idempotency_prefix = payload["idempotency_key"].startswith(
            "cmp-recipient-list-import:registrations:"
        )
        self.assertTrue(has_expected_idempotency_prefix)
        self.assertNotIn("members", payload)


class DatamailerImportPollingAssertionsMixin:
    def configure_successful_import_polling(
        self, recipient_list_import, job_id
    ):
        processing_response = {
            "import_job": {"id": job_id, "status": "processing"}
        }
        success_response = {
            "import_job": {
                "id": job_id,
                "status": "succeeded",
                "row_count": 1,
                "created_count": 1,
                "updated_count": 0,
                "removed_count": 0,
            }
        }
        recipient_list_import.side_effect = [
            processing_response,
            success_response,
        ]

    def assert_import_waited_for_success(self, expectation):
        self.assertEqual(expectation.recipient_list_import.call_count, 2)
        list_key = course_enrolled_list_key(expectation.course)
        expectation.recipient_list_import.assert_called_with(
            list_key,
            expectation.job_id,
        )
        output = expectation.out.getvalue()
        success_message = (
            f"Import job succeeded for "
            f"{list_key}: "
            f"job_id={expectation.job_id}"
        )
        self.assertIn(
            success_message,
            output,
        )


class DatamailerRecipientListCommandTestBase(
    DatamailerRecipientListFixtureMixin,
    DatamailerRecipientListBulkUpsertMixin,
    DatamailerRecipientListImportSetupMixin,
    DatamailerRegistrationImportAssertionsMixin,
    DatamailerImportPollingAssertionsMixin,
    TestCase,
):
    pass
