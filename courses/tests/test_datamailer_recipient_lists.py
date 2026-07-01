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
from courses.models import (
    Course,
    CourseRegistration,
    RegistrationCampaign,
)
from courses.tests.datamailer_recipient_lists_base import (
    BulkUpsertMemberExpectation,
    DATAMAILER_SETTINGS,
    DatamailerRecipientListCommandTestBase,
)


class DatamailerRecipientListCommandTest(
    DatamailerRecipientListCommandTestBase
):

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
