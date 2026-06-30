from dataclasses import dataclass
from datetime import timedelta
import json
from unittest.mock import Mock, patch
from io import StringIO

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import (
    course_enrolled_list_key,
    course_graduates_list_key,
    contact_tags_for_course,
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
    registration_list_key,
)
from course_management.datamailer.payloads import (
    RecipientListMemberPayload,
    certificate_availability_notification_payload,
    contact_payload_for_user,
    course_graduate_recipient_list_payload,
    datamailer_send_counts,
    enrollment_recipient_list_payload,
    homework_score_notification_payload,
    peer_review_assignment_notification_payload,
    project_passed_recipient_list_payload,
    project_score_notification_payload,
    registration_confirmation_payload,
)
from course_management.datamailer.sync import (
    erase_contact_from_datamailer,
    remove_enrollment_from_datamailer,
    remove_homework_submission_from_datamailer,
    remove_project_submission_from_datamailer,
    remove_registration_from_datamailer,
    send_certificate_availability_notification,
    send_homework_score_notification,
    send_peer_review_assignment_notification,
    send_project_score_notification,
    send_registration_confirmation_email,
    send_transactional_email,
    sync_contact,
    sync_enrollment_to_datamailer,
    sync_homework_submission_to_datamailer,
    sync_project_passed_outcome_to_datamailer,
    sync_project_submission_to_datamailer,
    sync_registration_to_datamailer,
)
from course_management.datamailer_outbox import _status_for_error
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    Homework,
    PeerReview,
    Project,
    ProjectState,
    ProjectSubmission,
    RegistrationCampaign,
    Submission,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class UpsertedRecipientMemberExpectation:
    upsert_member: Mock
    list_key: str
    source_object_key: str
    list_type: str


@dataclass(frozen=True)
class ScorePayloadExpectation:
    payload: dict
    template_key: str
    idempotency_key: str
    footer_text: str
    list_type: str


@dataclass(frozen=True)
class BulkUpsertMemberExpectation:
    bulk_upsert: Mock
    list_key: str
    source_object_key: str
    list_type: str | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class RecipientListAuditRepairExpectation:
    reconcile: Mock
    list_key: str
    source_object_key: str
    output: str


@dataclass(frozen=True)
class RecipientListAuditTarget:
    enrollment: Enrollment
    member_payload: RecipientListMemberPayload


@dataclass(frozen=True)
class ImportWaitExpectation:
    recipient_list_import: Mock
    course: Course
    job_id: int
    out: StringIO


@dataclass(frozen=True)
class ProjectScoreListSendExpectation:
    result: dict
    bulk_upsert: Mock
    send_list: Mock
    project: Project
    submission: ProjectSubmission


@dataclass(frozen=True)
class HomeworkScoreListSendExpectation:
    result: dict
    bulk_upsert: Mock
    send_list: Mock
    homework: Homework


class DatamailerWorkflowTest(TestCase):
    def http_error(self, status_code):
        exc = requests.HTTPError("request failed")
        exc.response = Mock(status_code=status_code)
        return exc

    def outbox_attempt(self, attempt_count=1, max_attempts=3):
        return Mock(attempt_count=attempt_count, max_attempts=max_attempts)

    def test_outbox_status_for_error_classifies_retryable_errors(self):
        self.assertEqual(
            _status_for_error(self.http_error(429), self.outbox_attempt()),
            DatamailerOutboxStatus.RETRYING,
        )
        self.assertEqual(
            _status_for_error(self.http_error(503), self.outbox_attempt()),
            DatamailerOutboxStatus.RETRYING,
        )

    def test_outbox_status_for_error_classifies_failed_errors(self):
        self.assertEqual(
            _status_for_error(self.http_error(400), self.outbox_attempt()),
            DatamailerOutboxStatus.FAILED,
        )
        self.assertEqual(
            _status_for_error(
                requests.RequestException("network error"),
                self.outbox_attempt(attempt_count=3, max_attempts=3),
            ),
            DatamailerOutboxStatus.FAILED,
        )

    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_homework(self, course=None):
        return Homework.objects.create(
            course=course or self.create_ml_course(),
            slug="homework-1",
            title="Homework 1",
            due_date="2026-01-01T00:00:00Z",
        )

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

    def create_student_enrollment_for_ml_course(self):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        return self.create_enrollment(user, self.create_ml_course())

    def create_certificate_enrollment(self):
        user = CustomUser.objects.create(
            email="student@example.com",
            username="student",
        )
        course = self.create_ml_course()
        return self.create_enrollment(
            user,
            course,
            certificate_url="/certificates/student.pdf",
        )

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

    def create_llm_registration_for_confirmation(self):
        course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=course,
        )
        return CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
            email="Student@Example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

    def create_homework_submission(self, homework, user, **overrides):
        enrollment = overrides.pop("enrollment", None)
        if enrollment is None:
            enrollment = self.create_enrollment(user, homework.course)
        defaults = {
            "homework": homework,
            "student": user,
            "enrollment": enrollment,
        }
        defaults.update(overrides)
        return Submission.objects.create(**defaults)

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

    def assert_upserted_recipient_member(self, expectation):
        expectation.upsert_member.assert_called_once()
        self.assertEqual(
            expectation.upsert_member.call_args.args[0],
            expectation.list_key,
        )
        self.assertEqual(
            expectation.upsert_member.call_args.args[1],
            expectation.source_object_key,
        )
        self.assertEqual(
            expectation.upsert_member.call_args.args[2]["list"]["type"],
            expectation.list_type,
        )

    def assert_project_passed_member_upserted(self, upsert_member, project):
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            project_passed_list_key(project),
        )
        payload = upsert_member.call_args.args[2]
        self.assertEqual(payload["member"]["status"], "active")
        self.assertEqual(
            payload["member"]["metadata"]["outcome"],
            "project_passed",
        )

    def create_failed_project_submission_for_passed_outcome(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("student@example.com"),
            total_score=50,
            passed=False,
        )
        return project, submission

    def assert_project_passed_member_removed(
        self,
        remove_member,
        project,
        submission,
    ):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            project_passed_list_key(project),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"project-submission:{submission.pk}",
        )

    def assert_homework_submission_member_removed(
        self,
        remove_member,
        homework,
        submission,
    ):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            homework_submitters_list_key(homework),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"homework-submission:{submission.pk}",
        )

    def assert_score_payload_common(self, expectation):
        payload = expectation.payload
        self.assertEqual(payload["template_key"], expectation.template_key)
        self.assertEqual(
            payload["idempotency_key"],
            expectation.idempotency_key,
        )
        self.assertEqual(payload["from_email"], "courses")
        self.assertEqual(
            payload["context"]["profile_url"],
            "https://courses.example.com/accounts/settings/",
        )
        self.assertIn(
            expectation.footer_text,
            payload["context"]["notification_footer"],
        )
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_submission_confirmations",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertNotIn("member_sync", payload)
        self.assertNotIn("remove_absent_members", payload)
        self.assertEqual(payload["list"]["type"], expectation.list_type)
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

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

    def create_project_submission_removal_fixture(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("student@example.com"),
            total_score=98,
            passed=True,
        )
        return project, submission

    def assert_project_submission_members_removed(
        self,
        remove_member,
        project,
        submission,
    ):
        self.assertEqual(remove_member.call_count, 2)
        list_keys = []
        remove_calls = remove_member.call_args_list
        for call in remove_calls:
            list_key = call.args[0]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [project_submitters_list_key(project), project_passed_list_key(project)],
        )
        for call in remove_calls:
            self.assertEqual(call.args[1], f"project-submission:{submission.pk}")

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

    def assert_registration_confirmation_payload(self, payload, registration):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["template_key"], "registration-confirmation")
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(
            payload["idempotency_key"],
            f"registration-confirmation:{registration.pk}",
        )
        self.assertEqual(
            payload["context"]["registration_url"],
            "https://courses.example.com/register/llm-zoomcamp/",
        )
        self.assertEqual(
            payload["context"]["course_url"],
            "https://courses.example.com/llm-zoomcamp-2026/",
        )
        self.assertEqual(payload["metadata"]["event"], "course_registration")
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_course_updates",
        )

    def configure_registration_confirmation_send_success(self, send):
        send.return_value = {
            "message": {
                "id": "message-id",
                "status": "queued",
                "template_key": "registration-confirmation",
            },
            "enqueued": True,
        }

    def assert_registration_confirmation_audit(self):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(
            audit.send_type,
            DatamailerSendAuditType.TRANSACTIONAL,
        )
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.template_key, "registration-confirmation")
        self.assertEqual(audit.category_tag, "course-updates")
        self.assertEqual(audit.event, "course_registration")

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

    def assert_registration_contact_synced(self, upsert_contact):
        upsert_contact.assert_called_once()
        self.assertEqual(
            upsert_contact.call_args.args[0]["tags"],
            ["course-ml-zoomcamp", "course-cohort-ml-zoomcamp-2026"],
        )

    def assert_registration_member_synced(self, upsert_member, registration):
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            registration_list_key(registration),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"registration:{registration.pk}",
        )
        self.assertEqual(
            upsert_member.call_args.args[2]["member"]["email"],
            "student@example.com",
        )

    def assert_registration_outbox_event(self, registration):
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.member_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, "email:student@example.com")
        self.assertEqual(
            event.payload["list_key"], registration_list_key(registration)
        )
        self.assertEqual(
            event.payload["source_object_key"],
            f"registration:{registration.pk}",
        )

    def assert_registration_member_removed(self, remove_member, registration):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            registration_list_key(registration),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"registration:{registration.pk}",
        )
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.member_remove",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            event.payload["member_payload"]["member"]["status"],
            "removed",
        )

    def mark_outbox_event_due(self):
        event = DatamailerOutboxEvent.objects.get()
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["next_attempt_at"])
        return event

    def assert_successful_outbox_dispatch_run(self):
        run = DatamailerOutboxDispatchRun.objects.get()
        self.assertEqual(run.status, DatamailerOutboxDispatchRunStatus.SUCCESS)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.processed_count, 1)
        self.assertEqual(run.acked_count, 1)
        self.assertEqual(run.retrying_count, 0)
        self.assertEqual(run.failed_count, 0)

    def assert_certificate_availability_payload(self, payload, enrollment):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(
            payload["template_key"],
            "certificate-availability-notification",
        )
        self.assertEqual(
            payload["idempotency_key"],
            f"certificate-available:{enrollment.pk}",
        )
        self.assertEqual(payload["from_email"], "courses")
        self.assertEqual(
            payload["context"]["certificate_url"],
            "https://courses.example.com/certificates/student.pdf",
        )
        self.assertEqual(
            payload["context"]["course_url"],
            "https://courses.example.com/ml-zoomcamp-2026/",
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "certificate_availability",
        )
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_course_updates",
        )
        self.assertIn(
            "Congratulations",
            payload["context"]["intro_text"],
        )
        self.assertEqual(
            payload["context"]["notification_category"],
            "course-related emails",
        )

    def create_recipient_list_audit_target(self):
        enrollment = self.create_enrolled_student()
        member_payload = enrollment_recipient_list_payload(enrollment)
        return RecipientListAuditTarget(
            enrollment=enrollment,
            member_payload=member_payload,
        )

    def audit_enrollment_recipient_list(
        self,
        course,
        *,
        repair=False,
        extra_args=None,
    ):
        out = StringIO()
        command_args = [
            "audit_datamailer_recipient_lists",
            "enrollments",
            "--course-slug",
            course.slug,
        ]
        if repair:
            command_args.append("--repair")
        if extra_args:
            command_args.extend(extra_args)
        call_command(*command_args, stdout=out)
        return out.getvalue()

    def configure_matching_recipient_list_member(
        self,
        recipient_list_members,
        source_object_key,
        payload,
    ):
        recipient_list_members.return_value = {
            "has_more": False,
            "members": [
                {
                    "source_object_key": source_object_key,
                    "email": payload["member"]["email"],
                    "status": "active",
                    "metadata": payload["member"]["metadata"],
                }
            ],
        }

    def configure_unexpected_recipient_list_member(self, recipient_list_members):
        recipient_list_members.return_value = {
            "has_more": False,
            "members": [
                {
                    "source_object_key": "user:999",
                    "email": "old@example.com",
                    "status": "active",
                    "metadata": {},
                }
            ],
        }

    def assert_recipient_list_audit_repaired(self, expectation):
        expectation.reconcile.assert_called_once()
        self.assertEqual(
            expectation.reconcile.call_args.args[0],
            expectation.list_key,
        )
        repaired_payload = expectation.reconcile.call_args.args[1]
        self.assertEqual(
            repaired_payload["members"][0]["source_object_key"],
            expectation.source_object_key,
        )
        self.assertIn(
            f"missing: {expectation.source_object_key}",
            expectation.output,
        )
        self.assertIn("unexpected: user:999", expectation.output)
        self.assertIn(
            f"Repaired {expectation.list_key}: upserted=1 removed=1",
            expectation.output,
        )
        self.assertIn("drifted=1", expectation.output)

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

    def assert_homework_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"homework-submission:{submission.pk}",
        )
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["questions_score"], 6)
        self.assertEqual(
            member["metadata"]["learning_in_public_score"], 2
        )
        self.assertEqual(member["metadata"]["faq_score"], 1)
        self.assertEqual(member["metadata"]["total_score"], 9)
        self.assertEqual(
            member["metadata"]["homework_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )

    def single_homework_score_member(self, payload):
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def single_project_score_member(self, payload):
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def create_contact_payload_fixture(self):
        user = CustomUser.objects.create(
            email="Student@Example.com",
            username="student",
        )
        return user, self.create_ml_course()

    def assert_course_subscription_contact_payload(self, payload):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertEqual(payload["status"], "subscribed")
        self.assertTrue(payload["verified"])
        self.assertEqual(
            payload["email_validation"]["status"],
            "externally_validated",
        )
        self.assertEqual(
            payload["tags"],
            [
                "course-ml-zoomcamp",
                "course-cohort-ml-zoomcamp-2026",
            ],
        )
        self.assertEqual(
            payload["custom_fields"]["course_slug"],
            "ml-zoomcamp-2026",
        )
        self.assertEqual(
            payload["custom_fields"]["course_family_slug"],
            "ml-zoomcamp",
        )
        self.assertEqual(
            payload["custom_fields"]["course_cohort_slug"],
            "ml-zoomcamp-2026",
        )

    def configure_contact_bulk_import_counts(self, bulk_import):
        bulk_import.return_value = {
            "counts": {
                "created": 1,
                "updated": 1,
                "unchanged": 0,
                "skipped": 0,
                "invalid": 0,
            },
        }

    def create_contact_backfill_users(self):
        CustomUser.objects.create_user(
            username="student-1",
            email="Student1@Example.com",
        )
        CustomUser.objects.create_user(
            username="student-2",
            email="student2@example.com",
        )

    def assert_first_contact_import_payload(self, bulk_import):
        self.assertEqual(bulk_import.call_count, 2)
        first_payload = bulk_import.call_args_list[0].args[0]
        self.assertEqual(first_payload["audience"], "dtc-courses")
        self.assertEqual(first_payload["client"], "dtc-courses")
        self.assertEqual(
            first_payload["idempotency_key"],
            "cmp-contact-bootstrap:1",
        )
        self.assertEqual(
            first_payload["contacts"][0]["email"],
            "student1@example.com",
        )
        self.assertEqual(
            first_payload["contacts"][0]["email_validation"]["status"],
            "externally_validated",
        )

    def assert_contact_import_output(self, out):
        self.assertIn(
            "Prepared 2 contact batch(es), 2 contact(s).",
            out.getvalue(),
        )
        self.assertIn("Synced batch 1: 1 contact(s); created=1", out.getvalue())

    def create_duplicate_homework_submissions(self):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        enrollment = self.create_enrollment(user, homework.course)
        self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=timezone.now() - timedelta(days=1),
            total_score=4,
        )
        latest_submission = self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=timezone.now(),
            total_score=9,
        )
        return homework, latest_submission

    def create_duplicate_project_submissions(self):
        project = self.create_project()
        user = self.create_user("project-learner@example.com")
        enrollment = self.create_enrollment(user, project.course)
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/old",
            submitted_at=timezone.now() - timedelta(days=1),
            total_score=40,
        )
        latest_submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/new",
            submitted_at=timezone.now(),
            total_score=90,
        )
        return project, latest_submission

    def create_project_score_submission(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("project-learner@example.com"),
            project_score=70,
            project_learning_in_public_score=5,
            project_faq_score=1,
            peer_review_score=18,
            peer_review_learning_in_public_score=4,
            total_score=98,
            reviewed_enough_peers=True,
            passed=True,
        )
        return project, submission

    def assert_project_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{submission.pk}",
        )
        self.assertEqual(member["email"], "project-learner@example.com")
        self.assertEqual(member["metadata"]["project_score"], 70)
        self.assertEqual(
            member["metadata"]["project_learning_in_public_score"],
            5,
        )
        self.assertEqual(member["metadata"]["project_faq_score"], 1)
        self.assertEqual(member["metadata"]["peer_review_score"], 18)
        self.assertEqual(
            member["metadata"]["peer_review_learning_in_public_score"],
            4,
        )
        self.assertEqual(member["metadata"]["total_score"], 98)
        self.assertEqual(
            member["metadata"]["github_link"],
            "https://github.com/example/project",
        )
        self.assertEqual(member["metadata"]["commit_id"], "abc123")
        self.assertEqual(
            member["metadata"]["project_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1",
        )
        self.assertTrue(member["metadata"]["reviewed_enough_peers"])
        self.assertTrue(member["metadata"]["passed"])

    def assert_project_score_context(self, payload):
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/results",
        )
        self.assertEqual(
            payload["context"]["project_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )

    def assert_latest_project_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{submission.pk}",
        )
        self.assertEqual(member["metadata"]["total_score"], 90)

    def assert_project_score_list_send(self, expectation):
        self.assertEqual(expectation.result, {"enqueued_count": 1})
        self.assertEqual(expectation.bulk_upsert.call_count, 2)
        expectation.send_list.assert_called_once()
        self.assertEqual(
            DatamailerOutboxEvent.objects.filter(
                event_type="recipient_list.members_bulk_upsert",
                status=DatamailerOutboxStatus.ACKED,
            ).count(),
            2,
        )
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            project_submitters_list_key(expectation.project),
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])
        self.assertEqual(
            expectation.bulk_upsert.call_args_list[1].args[0],
            project_passed_list_key(expectation.project),
        )
        passed_payload = expectation.bulk_upsert.call_args_list[1].args[1]
        self.assertEqual(
            passed_payload["members"][0]["source_object_key"],
            f"project-submission:{expectation.submission.pk}",
        )
        self.assertEqual(
            passed_payload["members"][0]["metadata"]["outcome"],
            "project_passed",
        )

    def assert_homework_score_list_send(self, expectation):
        self.assertEqual(expectation.result["enqueued_count"], 1)
        expectation.bulk_upsert.assert_called_once()
        expectation.send_list.assert_called_once()
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            homework_submitters_list_key(expectation.homework),
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.RECIPIENT_LIST)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(
            audit.list_key,
            homework_submitters_list_key(expectation.homework),
        )
        self.assertEqual(audit.template_key, "homework-score-notification")
        self.assertEqual(audit.category_tag, "submission-results")
        self.assertEqual(audit.event, "homework_score_publication")
        self.assertEqual(audit.intended_count, 1)
        self.assertEqual(audit.enqueued_count, 1)
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            event.payload["list_key"],
            homework_submitters_list_key(expectation.homework),
        )

    def transactional_email_payload(self):
        return {
            "template_key": "welcome",
            "email": "student@example.com",
            "idempotency_key": "welcome:student",
            "category_tag": "course-updates",
            "metadata": {
                "source": "course-management-platform",
                "event": "welcome",
            },
        }

    def configure_transactional_send_success(self, send):
        send.return_value = {
            "message": {
                "id": "message-id",
                "status": "queued",
                "template_key": "welcome",
            },
            "enqueued": True,
            "idempotent_replay": False,
        }

    def assert_transactional_send_called(self, send):
        expected_payload = self.transactional_email_payload()
        expected_payload.update(
            {
                "audience": "dtc-courses",
                "client": "dtc-courses",
            }
        )
        send.assert_called_once_with(expected_payload)

    def assert_transactional_send_audit(self):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.TRANSACTIONAL)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.idempotency_key, "welcome:student")
        self.assertEqual(audit.template_key, "welcome")
        self.assertEqual(audit.category_tag, "course-updates")
        self.assertEqual(audit.source, "course-management-platform")
        self.assertEqual(audit.event, "welcome")
        self.assertEqual(audit.intended_count, 1)
        self.assertEqual(audit.enqueued_count, 1)
        self.assertEqual(audit.skipped_count, 0)

    def create_peer_review_assignment_fixture(self):
        project = self.create_project(
            state=ProjectState.PEER_REVIEWING.value,
            number_of_peers_to_evaluate=3,
            # Summer instant: PT 15:00, Berlin 00:00 next day.
            peer_review_due_date="2026-07-02T22:00:00Z",
        )
        submissions = []
        for i in range(4):
            user = self.create_user(f"learner-{i}@example.com")
            if i == 0:
                user.preferred_timezone = "Europe/Berlin"
                user.save(update_fields=["preferred_timezone"])
            submission = self.create_project_submission(
                project,
                user,
                github_link=f"https://github.com/example/p{i}",
            )
            submissions.append(submission)

        reviewer = submissions[0]
        targets = submissions[1:]
        for target in targets:
            PeerReview.objects.create(
                reviewer=reviewer,
                submission_under_evaluation=target,
                note_to_peer="",
                optional=False,
            )
        PeerReview.objects.create(
            reviewer=reviewer,
            submission_under_evaluation=targets[0],
            note_to_peer="",
            optional=True,
        )
        project.refresh_from_db()
        return project

    def assert_peer_review_assignment_payload(self, payload, project):
        self.assertEqual(payload["template_key"], "peer-review-assignment")
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertEqual(
            payload["idempotency_key"],
            "peer-review-assignment:ml-zoomcamp-2026:project-1",
        )
        self.assertEqual(payload["metadata"]["event"], "peer_review_assignment")
        context = payload["context"]
        self.assertEqual(context["number_of_peers_to_evaluate"], 3)
        self.assertEqual(
            context["peer_review_due_at"],
            project.peer_review_due_date.isoformat(),
        )
        self.assertEqual(context["deadline_weekday"], "Thursday")
        self.assertEqual(context["deadline_time"], "22:00")
        self.assertEqual(
            context["deadline_summary"], "Thursday, 2 July 2026, 22:00 UTC"
        )

    def assert_berlin_reviewer_assignments(self, payload):
        members_by_email = {}
        members = payload["members"]
        for member in members:
            email = member["email"]
            members_by_email[email] = member
        self.assertEqual(len(members_by_email), 4)
        reviewer_member = members_by_email["learner-0@example.com"]
        self.assertEqual(
            reviewer_member["metadata"]["deadline_summary"],
            "Friday, 3 July 2026, 00:00 Europe/Berlin",
        )
        self.assertEqual(
            reviewer_member["metadata"]["deadline_timezone"],
            "Europe/Berlin",
        )
        assigned = reviewer_member["metadata"]["assigned_reviews"]
        self.assertEqual(reviewer_member["metadata"]["assigned_reviews_count"], 3)
        self.assertEqual(len(assigned), 3)
        for item in assigned:
            self.assertIn(
                f"/ml-zoomcamp-2026/project/project-1/eval/{item['review_id']}",
                item["eval_url"],
            )
            self.assertTrue(item["eval_url"].startswith("https://"))

    @override_settings(**DATAMAILER_SETTINGS)
    def test_contact_payload_includes_course_subscription_data(self):
        user, course = self.create_contact_payload_fixture()

        payload = contact_payload_for_user(user, course=course)

        self.assert_course_subscription_contact_payload(payload)

    def test_contact_tags_for_course_without_trailing_year(self):
        course = Course(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )

        self.assertEqual(
            contact_tags_for_course(course),
            [
                "course-ml-zoomcamp",
                "course-cohort-ml-zoomcamp",
            ],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_contact_logs_and_continues_on_api_failure(
        self, upsert
    ):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        sync_contact(user)

        upsert.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_STRICT=True)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_contact_can_be_strict(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        with self.assertRaises(requests.RequestException):
            sync_contact(user)

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_FROM_EMAIL="")
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_uses_datamailer_client(
        self, send
    ):
        self.configure_transactional_send_success(send)

        result = send_transactional_email(self.transactional_email_payload())

        self.assertEqual(result["message"]["id"], "message-id")
        self.assert_transactional_send_called(send)
        self.assert_transactional_send_audit()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_FROM_EMAIL="")
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_audits_api_failure(self, send):
        send.side_effect = requests.RequestException("network error")

        result = send_transactional_email(self.transactional_email_payload())

        self.assertIsNone(result)
        self.assert_transactional_send_called(send)
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.TRANSACTIONAL)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertEqual(audit.idempotency_key, "welcome:student")
        self.assertEqual(audit.error, "network error")

    def test_datamailer_send_counts_marks_transactional_replay(self):
        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSACTIONAL,
            {},
            {
                "idempotent_replay": True,
                "enqueued": False,
                "message": {"status": "skipped"},
            },
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["created_count"], 0)
        self.assertEqual(counts["enqueued_count"], 0)
        self.assertEqual(counts["skipped_count"], 1)
        self.assertEqual(counts["idempotent_replay_count"], 1)

    def test_datamailer_send_counts_uses_recipient_list_response(self):
        counts = datamailer_send_counts(
            DatamailerSendAuditType.RECIPIENT_LIST,
            {},
            {
                "recipient_list": {"active_member_count": 3},
                "created_count": 2,
                "enqueued_count": 1,
                "skipped_count": 1,
            },
        )

        self.assertEqual(counts["intended_count"], 3)
        self.assertEqual(counts["created_count"], 2)
        self.assertEqual(counts["enqueued_count"], 1)
        self.assertEqual(counts["skipped_count"], 1)

    def test_datamailer_send_counts_falls_back_to_transient_members(self):
        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            {
                "members": [
                    {"email": "active@example.com"},
                    {"email": "removed@example.com", "status": "removed"},
                ],
            },
            {"transient_recipient_list": {}, "enqueued_count": 1},
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["enqueued_count"], 1)

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_adds_configured_from_email(
        self, send
    ):
        send.return_value = {"id": "message-id"}

        send_transactional_email(
            {
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

        send.assert_called_once_with(
            {
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "courses",
            }
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_keeps_explicit_from_email(
        self, send
    ):
        send.return_value = {"id": "message-id"}

        send_transactional_email(
            {
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "no-reply",
            }
        )

        send.assert_called_once_with(
            {
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "no-reply",
            }
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_registration_confirmation_payload(self):
        registration = self.create_llm_registration_for_confirmation()

        payload = registration_confirmation_payload(registration)

        self.assert_registration_confirmation_payload(payload, registration)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_registration_confirmation_email_uses_transactional_send(
        self, send
    ):
        self.configure_registration_confirmation_send_success(send)
        registration = self.create_llm_registration_for_confirmation()

        result = send_registration_confirmation_email(registration)

        self.assertEqual(result["message"]["id"], "message-id")
        send.assert_called_once()
        self.assert_registration_confirmation_payload(
            send.call_args.args[0],
            registration,
        )
        self.assert_registration_confirmation_audit()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.client.DatamailerClient.erase_contact")
    def test_erase_contact_enqueues_outbox_event(self, erase_contact):
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )

        erase_contact_from_datamailer(user)

        erase_contact.assert_called_once_with("student@example.com")
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(event.event_type, "contact.erase")
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, f"user:{user.pk}")
        self.assertEqual(
            event.idempotency_key,
            f"contact.erase:user:{user.pk}:student@example.com",
        )
        self.assertEqual(
            event.payload,
            {
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "user_id": user.pk,
            },
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.client.DatamailerClient.erase_contact")
    def test_erase_contact_enqueues_outbox_event_for_email(
        self, erase_contact
    ):
        erase_contact_from_datamailer(email=" Student@Example.com ")

        erase_contact.assert_called_once_with("student@example.com")
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(event.event_type, "contact.erase")
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, "email:student@example.com")
        self.assertEqual(
            event.idempotency_key,
            "contact.erase:email:student@example.com:student@example.com",
        )
        self.assertEqual(
            event.payload,
            {
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "user_id": None,
            },
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_registration_adds_contact_and_registrant_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        registration = self.create_registration()

        sync_registration_to_datamailer(registration)

        self.assert_registration_contact_synced(upsert_contact)
        self.assert_registration_member_synced(upsert_member, registration)
        self.assert_registration_outbox_event(registration)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_membership_sync_failure_records_retryable_outbox_event(
        self,
        upsert_contact,
        upsert_member,
    ):
        upsert_member.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )

        sync_enrollment_to_datamailer(enrollment)

        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.member_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.attempt_count, 1)
        self.assertIn("network error", event.last_error)
        self.assertEqual(event.ordering_key, f"user:{user.pk}")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_process_datamailer_outbox_retries_due_events(
        self,
        upsert_contact,
        upsert_member,
    ):
        upsert_member.side_effect = [
            requests.RequestException("network error"),
            {"ok": True},
        ]
        enrollment = self.create_student_enrollment_for_ml_course()
        sync_enrollment_to_datamailer(enrollment)
        event = self.mark_outbox_event_due()

        out = StringIO()
        call_command("process_datamailer_outbox", stdout=out)

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.attempt_count, 2)
        self.assertEqual(upsert_contact.call_count, 2)
        self.assertEqual(upsert_member.call_count, 2)
        self.assertIn("1 acked", out.getvalue())
        self.assert_successful_outbox_dispatch_run()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_datamailer_outbox_status_reports_counts_and_last_error(
        self,
        upsert_contact,
        upsert_member,
    ):
        upsert_member.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        sync_enrollment_to_datamailer(enrollment)
        event = DatamailerOutboxEvent.objects.get()
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["next_attempt_at"])

        out = StringIO()
        call_command("datamailer_outbox_status", stdout=out)

        output = out.getvalue()
        self.assertIn("retrying: 1", output)
        self.assertIn("due: 1", output)
        self.assertIn(event.event_id, output)
        self.assertIn("last_successful_run: none", output)
        self.assertIn("last_datamailer_error:", output)
        self.assertIn("network error", output)

    def test_datamailer_send_status_reports_counts_and_failures(self):
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key="registration:1",
            template_key="registration-confirmation",
            category_tag="course-updates",
            event="registration",
            intended_count=1,
            created_count=1,
            enqueued_count=1,
        )
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.FAILED,
            idempotency_key="deadline-reminder:homework:1:24h",
            template_key="deadline-reminder",
            category_tag="deadline-reminders",
            event="deadline_reminder",
            list_key="deadline-reminders:homework:ml-zoomcamp:hw1:24h",
            intended_count=3,
            error="network error",
        )

        out = StringIO()
        call_command("datamailer_send_status", stdout=out)

        output = out.getvalue()
        self.assertIn("Datamailer send status", output)
        self.assertIn("total_sends: 2", output)
        self.assertIn("succeeded: 1", output)
        self.assertIn("failed: 1", output)
        self.assertIn("intended: 4", output)
        self.assertIn("enqueued: 1", output)
        self.assertIn("deadline-reminders: 1", output)
        self.assertIn("recent_failures:", output)
        self.assertIn("deadline-reminder:homework:1:24h", output)
        self.assertIn("network error", output)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_enrollment_recipient_list_payload_targets_course_enrolled(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )

        member_payload = enrollment_recipient_list_payload(enrollment)

        self.assertEqual(
            member_payload.list_key,
            course_enrolled_list_key(course),
        )
        self.assertEqual(member_payload.source_object_key, f"user:{user.pk}")
        payload = member_payload.payload
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["list"]["name"],
            "ML Zoomcamp 2026 enrolled learners",
        )
        self.assertEqual(
            payload["member"]["email"],
            "student@example.com",
        )
        self.assertEqual(
            payload["member"]["metadata"]["enrollment_id"],
            enrollment.pk,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_enrollment_adds_contact_and_enrolled_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )

        sync_enrollment_to_datamailer(enrollment)

        upsert_contact.assert_called_once()
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            course_enrolled_list_key(course),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"user:{user.pk}",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_homework_submission_adds_submitter_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        homework = self.create_homework()
        submission = self.create_homework_submission(
            homework,
            self.create_user("student@example.com"),
        )

        sync_homework_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=homework_submitters_list_key(homework),
            source_object_key=f"homework-submission:{submission.pk}",
            list_type="homework_submitters",
        )
        self.assert_upserted_recipient_member(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_project_submission_adds_submitter_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        user = self.create_user("student@example.com")
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            user,
            commit_id="a" * 40,
        )

        sync_project_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=project_submitters_list_key(project),
            source_object_key=f"project-submission:{submission.pk}",
            list_type="project_submitters",
        )
        self.assert_upserted_recipient_member(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_registration_deletes_registrant_member(
        self,
        remove_member,
    ):
        registration = self.create_registration()

        remove_registration_from_datamailer(registration)

        self.assert_registration_member_removed(remove_member, registration)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_enrollment_removes_enrolled_and_graduate_members(
        self,
        remove_member,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
            certificate_url="/certificates/student.pdf",
        )

        remove_enrollment_from_datamailer(enrollment)

        self.assertEqual(remove_member.call_count, 2)
        list_keys = []
        remove_calls = remove_member.call_args_list
        for call in remove_calls:
            list_key = call.args[0]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [course_enrolled_list_key(course), course_graduates_list_key(course)],
        )
        source_object_keys = []
        for call in remove_calls:
            source_object_key = call.args[1]
            source_object_keys.append(source_object_key)
        self.assertEqual(
            source_object_keys,
            [f"user:{user.pk}", f"enrollment:{enrollment.pk}"],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_homework_submission_deletes_submitter_member(
        self,
        remove_member,
    ):
        homework = self.create_homework()
        submission = self.create_homework_submission(
            homework,
            self.create_user("student@example.com"),
        )

        remove_homework_submission_from_datamailer(submission)

        self.assert_homework_submission_member_removed(
            remove_member,
            homework,
            submission,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_project_submission_removes_submitter_and_passed_members(
        self,
        remove_member,
    ):
        project, submission = self.create_project_submission_removal_fixture()

        remove_project_submission_from_datamailer(submission)

        self.assert_project_submission_members_removed(
            remove_member,
            project,
            submission,
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_homework_score_notification_payload_targets_homework_submitters(
        self,
    ):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        submission = self.create_homework_submission(
            homework,
            user,
            questions_score=6,
            learning_in_public_score=2,
            faq_score=1,
            total_score=9,
        )

        list_key, payload = homework_score_notification_payload(
            homework
        )

        self.assertEqual(
            list_key, homework_submitters_list_key(homework)
        )
        expectation = ScorePayloadExpectation(
            payload=payload,
            template_key="homework-score-notification",
            idempotency_key="homework-score:ml-zoomcamp-2026:homework-1",
            footer_text="you submitted Homework 1",
            list_type="homework_submitters",
        )
        member = self.assert_score_payload_common(expectation)
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )
        self.assert_homework_score_member(member, submission)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_payload_dedupes_student_submissions(
        self,
    ):
        homework, latest_submission = self.create_duplicate_homework_submissions()

        _, payload = homework_score_notification_payload(homework)

        member = self.single_homework_score_member(payload)
        self.assertEqual(
            member["source_object_key"],
            f"homework-submission:{latest_submission.pk}",
        )
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 9)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_includes_submitters(self):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        self.create_homework_submission(homework, user, total_score=9)

        _, payload = homework_score_notification_payload(homework)

        member = self.single_homework_score_member(payload)
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 9)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_homework_score_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {
            "recipient_list": {
                "key": "ml-zoomcamp-2026:@e:@homework:homework-1",
                "active_member_count": 1,
            },
            "template_key": "homework-score-notification",
            "idempotency_key": "homework-score:ml-zoomcamp-2026:homework-1",
            "created_count": 1,
            "enqueued_count": 1,
            "skipped_count": 0,
            "idempotent_replay_count": 0,
        }
        homework = self.create_homework()

        result = send_homework_score_notification(homework)

        expectation = HomeworkScoreListSendExpectation(
            result=result,
            bulk_upsert=bulk_upsert,
            send_list=send_list,
            homework=homework,
        )
        self.assert_homework_score_list_send(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_score_notification_does_not_send_without_metadata_ack(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.side_effect = requests.RequestException("network error")
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        homework = Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date="2026-01-01T00:00:00Z",
        )

        result = send_homework_score_notification(homework)

        self.assertIsNone(result)
        send_list.assert_not_called()
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertIn("metadata sync", audit.error)

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_project_score_notification_payload_targets_project_submitters(
        self,
    ):
        project, submission = self.create_project_score_submission()

        list_key, payload = project_score_notification_payload(project)

        self.assertEqual(list_key, project_submitters_list_key(project))
        expectation = ScorePayloadExpectation(
            payload=payload,
            template_key="project-score-notification",
            idempotency_key="project-score:ml-zoomcamp-2026:project-1",
            footer_text="you submitted Project 1",
            list_type="project_submitters",
        )
        member = self.assert_score_payload_common(expectation)
        self.assert_project_score_context(payload)
        self.assert_project_score_member(member, submission)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_dedupes_student_submissions(self):
        project, latest = self.create_duplicate_project_submissions()

        _, payload = project_score_notification_payload(project)

        self.assert_latest_project_score_member(
            self.single_project_score_member(payload),
            latest,
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_project_passed_recipient_list_payload_targets_passed_outcome(
        self,
    ):
        project, passed_submission = (
            self.create_passed_and_failed_project_submissions()
        )

        list_key, payload = project_passed_recipient_list_payload(project)

        self.assertEqual(list_key, project_passed_list_key(project))
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["list"]["metadata"]["outcome"], "project_passed"
        )
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "passed@example.com")
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{passed_submission.pk}",
        )
        self.assertEqual(member["metadata"]["outcome"], "project_passed")
        self.assertEqual(member["metadata"]["total_score"], 98)
        self.assertTrue(member["metadata"]["passed"])

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_peer_review_assignment_payload_includes_links_and_deadline(self):
        project = self.create_peer_review_assignment_fixture()
        list_key, payload = peer_review_assignment_notification_payload(
            project
        )

        self.assertEqual(list_key, project_submitters_list_key(project))
        self.assert_peer_review_assignment_payload(payload, project)
        self.assert_berlin_reviewer_assignments(payload)

    @override_settings(PUBLIC_BASE_URL="https://courses.example.com")
    def test_preview_peer_review_email_prints_submission_previews(self):
        project = self.create_peer_review_assignment_fixture()

        out = StringIO()
        call_command(
            "preview_peer_review_email",
            project.course.slug,
            project.slug,
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Project:  Project 1 (project-1)", output)
        self.assertIn("- learner-0@example.com", output)
        self.assertIn("you were assigned 3 projects to review", output)
        self.assertIn(
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval/",
            output,
        )
        self.assertIn("(project: https://github.com/example/p1)", output)
        self.assertIn("4 recipient(s) would be emailed.", output)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_peer_review_assignment_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {
            "recipient_list": {"active_member_count": 4},
            "enqueued_count": 4,
        }
        project = self.create_peer_review_assignment_fixture()

        result = send_peer_review_assignment_notification(project)

        self.assertEqual(result["enqueued_count"], 4)
        bulk_upsert.assert_called_once()
        send_list.assert_called_once()
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            project_submitters_list_key(project),
        )
        self.assertEqual(len(bulk_upsert.call_args.args[1]["members"]), 4)
        self.assertEqual(
            send_list.call_args.args[0],
            project_submitters_list_key(project),
        )
        self.assertNotIn("members", send_list.call_args.args[1])
        self.assertNotIn("list", send_list.call_args.args[1])
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.RECIPIENT_LIST)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.event, "peer_review_assignment")
        self.assertEqual(audit.intended_count, 4)
        self.assertEqual(audit.enqueued_count, 4)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_includes_submitters(self):
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        project = Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            submission_due_date="2026-01-01T00:00:00Z",
            peer_review_due_date="2026-01-08T00:00:00Z",
        )
        user = CustomUser.objects.create_user(
            username="project-learner@example.com",
            email="project-learner@example.com",
            password="test",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/project",
            commit_id="abc123",
            total_score=98,
        )

        _, payload = project_score_notification_payload(project)

        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "project-learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 98)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_project_score_notification_bulk_upserts_passed_outcome_before_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {"enqueued_count": 1}
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("project-learner@example.com"),
            total_score=98,
            passed=True,
        )

        result = send_project_score_notification(project)

        expectation = ProjectScoreListSendExpectation(
            result=result,
            bulk_upsert=bulk_upsert,
            send_list=send_list,
            project=project,
            submission=submission,
        )
        self.assert_project_score_list_send(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch("course_management.datamailer.client.DatamailerClient.upsert_contact")
    def test_sync_project_passed_outcome_upserts_passed_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        project = self.create_project()
        submission = self.create_project_submission(
            project=project,
            user=self.create_user("student@example.com"),
            total_score=98,
            passed=True,
        )

        sync_project_passed_outcome_to_datamailer(submission)

        upsert_contact.assert_called_once()
        self.assert_project_passed_member_upserted(upsert_member, project)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_sync_project_passed_outcome_removes_failed_member(
        self,
        remove_member,
    ):
        project, submission = (
            self.create_failed_project_submission_for_passed_outcome()
        )

        sync_project_passed_outcome_to_datamailer(submission)

        self.assert_project_passed_member_removed(
            remove_member,
            project,
            submission,
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_certificate_availability_notification_payload(self):
        enrollment = self.create_certificate_enrollment()

        payload = certificate_availability_notification_payload(
            enrollment
        )

        self.assert_certificate_availability_payload(payload, enrollment)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_course_graduate_recipient_list_payload_targets_graduated_outcome(
        self,
    ):
        user = CustomUser.objects.create(
            email="student@example.com",
            username="student",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
            total_score=91,
            certificate_url="/certificates/student.pdf",
        )

        list_key, payload = course_graduate_recipient_list_payload(
            enrollment
        )

        self.assertEqual(list_key, course_graduates_list_key(course))
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(payload["list"]["metadata"]["outcome"], "course_graduated")
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "student@example.com")
        self.assertEqual(
            member["source_object_key"], f"enrollment:{enrollment.pk}"
        )
        self.assertEqual(member["metadata"]["outcome"], "course_graduated")
        self.assertEqual(member["metadata"]["total_score"], 91)
        self.assertEqual(
            member["metadata"]["certificate_url"],
            "https://courses.example.com/certificates/student.pdf",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_certificate_availability_notification_uses_datamailer_preference_category(
        self,
        bulk_upsert,
        send,
    ):
        bulk_upsert.return_value = {"updated_count": 1}
        send.return_value = {"id": 123}
        enrollment = self.create_certificate_enrollment()

        payload = certificate_availability_notification_payload(
            enrollment
        )
        result = send_certificate_availability_notification(enrollment)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(result, {"id": 123})
        bulk_upsert.assert_called_once()
        send.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_certificate_availability_notification_uses_transactional_send(
        self,
        bulk_upsert,
        send,
    ):
        bulk_upsert.return_value = {"updated_count": 1}
        send.return_value = {"id": 123}
        enrollment = self.create_certificate_enrollment()

        result = send_certificate_availability_notification(enrollment)

        self.assertEqual(result, {"id": 123})
        bulk_upsert.assert_called_once()
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            course_graduates_list_key(enrollment.course),
        )
        send.assert_called_once()
        payload = send.call_args.args[0]
        self.assertEqual(
            payload["template_key"],
            "certificate-availability-notification",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
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
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
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
        self.assertIn("Prepared 1 contact batch(es), 1 contact(s).", out.getvalue())
        self.assertIn("batch 1: 1 contact(s)", out.getvalue())

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
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
        self.assertEqual(len(payload["contacts"]), 1)
        self.assertEqual(payload["contacts"][0]["email"], "active@example.com")

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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.reconcile_recipient_list_members"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_members"
    )
    def test_recipient_list_audit_reports_no_drift(
        self,
        recipient_list_members,
        reconcile,
    ):
        target = self.create_recipient_list_audit_target()
        member_payload = target.member_payload
        self.configure_matching_recipient_list_member(
            recipient_list_members,
            member_payload.source_object_key,
            member_payload.payload,
        )

        output = self.audit_enrollment_recipient_list(target.enrollment.course)

        recipient_list_members.assert_called_once_with(
            member_payload.list_key,
            include_removed=False,
            limit=10000,
        )
        reconcile.assert_not_called()
        self.assertIn("missing=0 unexpected=0", output)
        self.assertIn("drifted=0", output)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.reconcile_recipient_list_members"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_members"
    )
    def test_recipient_list_audit_can_repair_drift(
        self,
        recipient_list_members,
        reconcile,
    ):
        reconcile.return_value = {"upsert_count": 1, "removed_count": 1}
        self.configure_unexpected_recipient_list_member(
            recipient_list_members
        )
        target = self.create_recipient_list_audit_target()
        member_payload = target.member_payload

        output = self.audit_enrollment_recipient_list(
            target.enrollment.course,
            repair=True,
        )

        expectation = RecipientListAuditRepairExpectation(
            reconcile=reconcile,
            list_key=member_payload.list_key,
            source_object_key=member_payload.source_object_key,
            output=output,
        )
        self.assert_recipient_list_audit_repaired(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_members"
    )
    def test_recipient_list_audit_rejects_truncated_member_listing(
        self,
        recipient_list_members,
    ):
        recipient_list_members.return_value = {"has_more": True, "members": []}
        target = self.create_recipient_list_audit_target()
        member_payload = target.member_payload

        with self.assertRaisesMessage(
            CommandError,
            "Datamailer returned more than 2 active members for "
            f"{member_payload.list_key}",
        ):
            self.audit_enrollment_recipient_list(
                target.enrollment.course,
                extra_args=["--limit", "2"],
            )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.recipient_list_members"
    )
    def test_recipient_list_audit_wraps_member_listing_errors(
        self,
        recipient_list_members,
    ):
        recipient_list_members.side_effect = requests.RequestException(
            "network error"
        )
        target = self.create_recipient_list_audit_target()
        member_payload = target.member_payload

        with self.assertRaisesMessage(
            CommandError,
            "Datamailer member listing failed for "
            f"{member_payload.list_key}: network error",
        ):
            self.audit_enrollment_recipient_list(target.enrollment.course)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_audit_rejects_invalid_options(self):
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
                ("registrations", "--limit", "0"),
                "--limit must be between 1 and 10000.",
            ),
        ]

        for args, message in cases:
            with self.subTest(args=args):
                with self.assertRaisesMessage(CommandError, message):
                    call_command("audit_datamailer_recipient_lists", *args)

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
