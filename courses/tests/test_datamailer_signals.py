from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    Homework,
    Project,
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


class DatamailerSignalTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.sync_contact")
    def test_new_user_syncs_after_commit(self, sync):
        with self.captureOnCommitCallbacks(execute=True):
            user = CustomUser.objects.create(email="student@example.com")

        sync.assert_called_once_with(user)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.sync_enrollment_recipient_list")
    def test_new_enrollment_syncs_after_commit(self, sync):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        sync.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            enrollment = Enrollment.objects.create(
                student=user,
                course=course,
            )

        sync.assert_called_once_with(enrollment)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.erase_contact_from_datamailer")
    def test_deleted_user_erases_contact_after_commit(self, erase_contact):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        user_id = user.pk

        with self.captureOnCommitCallbacks(execute=True):
            user.delete()

        erase_contact.assert_called_once_with(
            user_id=user_id,
            email="student@example.com",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.remove_registration_recipient_list")
    def test_deleted_registration_removes_member_after_commit(self, remove):
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            current_course=course,
        )
        registration = CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
            email="student@example.com",
            name="Student",
        )

        with self.captureOnCommitCallbacks(execute=True):
            registration.delete()

        remove.assert_called_once()
        self.assertEqual(remove.call_args.args[0].pk, registration.pk)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.remove_enrollment_recipient_list")
    def test_deleted_enrollment_removes_member_after_commit(self, remove):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(student=user, course=course)
        remove.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            enrollment.delete()

        remove.assert_called_once()
        self.assertEqual(remove.call_args.args[0].pk, enrollment.pk)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.remove_homework_submission_recipient_list")
    def test_deleted_homework_submission_removes_member_after_commit(
        self,
        remove,
    ):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(student=user, course=course)
        homework = Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date="2026-01-01T00:00:00Z",
        )
        submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
        )

        with self.captureOnCommitCallbacks(execute=True):
            submission.delete()

        remove.assert_called_once()
        self.assertEqual(remove.call_args.args[0].pk, submission.pk)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.remove_project_submission_recipient_list")
    def test_deleted_project_submission_removes_member_after_commit(
        self,
        remove,
    ):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        enrollment = Enrollment.objects.create(student=user, course=course)
        project = Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            submission_due_date="2026-01-01T00:00:00Z",
            peer_review_due_date="2026-01-08T00:00:00Z",
        )
        submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/project",
        )

        with self.captureOnCommitCallbacks(execute=True):
            submission.delete()

        remove.assert_called_once()
        self.assertEqual(remove.call_args.args[0].pk, submission.pk)
