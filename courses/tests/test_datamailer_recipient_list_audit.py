from dataclasses import dataclass
from io import StringIO
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.payloads.base import (
    RecipientListMemberPayload,
    enrollment_recipient_list_payload,
)
from courses.models import Course, Enrollment


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class RecipientListAuditRepairExpectation:
    reconcile: object
    list_key: str
    source_object_key: str
    output: str


@dataclass(frozen=True)
class RecipientListAuditTarget:
    enrollment: Enrollment
    member_payload: RecipientListMemberPayload


class DatamailerRecipientListAuditFixtureMixin:
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

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

    def create_enrolled_student(self):
        course = self.create_ml_course()
        user = self.create_user("student@example.com")
        return self.create_enrollment(user, course)

    def create_recipient_list_audit_target(self):
        enrollment = self.create_enrolled_student()
        member_payload = enrollment_recipient_list_payload(enrollment)
        return RecipientListAuditTarget(
            enrollment=enrollment,
            member_payload=member_payload,
        )


class DatamailerRecipientListAuditCommandMixin:
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


class DatamailerRecipientListAuditMemberMixin:
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


class DatamailerRecipientListAuditRepairAssertionsMixin:
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


class DatamailerRecipientListAuditNoDriftTest(
    DatamailerRecipientListAuditFixtureMixin,
    DatamailerRecipientListAuditCommandMixin,
    DatamailerRecipientListAuditMemberMixin,
    TestCase,
):
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


class DatamailerRecipientListAuditRepairTest(
    DatamailerRecipientListAuditFixtureMixin,
    DatamailerRecipientListAuditCommandMixin,
    DatamailerRecipientListAuditMemberMixin,
    DatamailerRecipientListAuditRepairAssertionsMixin,
    TestCase,
):
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


class DatamailerRecipientListAuditListingErrorTest(
    DatamailerRecipientListAuditFixtureMixin,
    DatamailerRecipientListAuditCommandMixin,
    TestCase,
):
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


class DatamailerRecipientListAuditOptionValidationTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    def test_recipient_list_audit_rejects_invalid_options(self):
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
                ("registrations", "--limit", "0"),
                "--limit must be between 1 and 10000.",
            ),
        ):
            with self.subTest(args=args):
                with self.assertRaisesMessage(CommandError, message):
                    call_command("audit_datamailer_recipient_lists", *args)
