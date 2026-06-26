from datetime import timedelta
from unittest.mock import Mock, patch
from io import StringIO

import requests
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from course_management.datamailer import (
    certificate_availability_notification_payload,
    course_enrolled_list_key,
    DatamailerClient,
    DatamailerConfig,
    contact_tags_for_course,
    contact_payload_for_user,
    datamailer_enabled,
    enrollment_recipient_list_payload,
    get_contact_history,
    get_contact_status,
    get_email_status,
    get_email_preferences_for_user,
    get_transactional_message_status,
    homework_score_notification_payload,
    homework_submitters_list_key,
    peer_review_assignment_notification_payload,
    project_score_notification_payload,
    project_submitters_list_key,
    registration_list_key,
    send_certificate_availability_notification,
    send_homework_score_notification,
    send_project_score_notification,
    send_transactional_email,
    sync_contact,
    sync_enrollment_to_datamailer,
    sync_homework_submission_to_datamailer,
    sync_project_submission_to_datamailer,
    sync_registration_to_datamailer,
    update_email_preferences_for_user,
)
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


class DatamailerClientTest(TestCase):
    def test_missing_env_disables_datamailer(self):
        with override_settings(
            DATAMAILER_URL="",
            DATAMAILER_API_KEY="",
            DATAMAILER_CLIENT="",
            DATAMAILER_AUDIENCE="",
        ):
            self.assertFalse(datamailer_enabled())

    def test_upsert_contact_uses_bearer_auth(self):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.upsert_contact({"email": "student@example.com"})

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "POST",
            "https://datamailer.example.com/api/contacts",
            json={"email": "student@example.com"},
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_contact_status_uses_configured_scope(self):
        session = Mock()
        response = Mock(content=b'{"exists": true}')
        response.json.return_value = {"exists": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/contacts/status",
            json=None,
            params={
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
            },
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_contact_history_uses_configured_scope(self):
        session = Mock()
        response = Mock(content=b'{"transactional_messages": []}')
        response.json.return_value = {"transactional_messages": []}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/contacts/42/history",
            json=None,
            params={
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "limit": 5,
            },
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_transactional_message_status_uses_message_id(self):
        session = Mock()
        response = Mock(content=b'{"message": {"id": 42}}')
        response.json.return_value = {"message": {"id": 42}}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/transactional/messages/42",
            json=None,
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_recipient_list_member_uses_expected_endpoint(self):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.upsert_recipient_list_member(
            "ml-zoomcamp-2026",
            "registration:42",
            {"email": "student@example.com"},
        )

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "PUT",
            "https://datamailer.example.com/api/recipient-lists/ml-zoomcamp-2026/members/registration:42",
            json={"email": "student@example.com"},
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_recipient_list_transactional_send_uses_expected_endpoint(
        self,
    ):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.send_recipient_list_transactional(
            "ml-zoomcamp-2026:@e:@homework:homework-1",
            {"template_key": "homework-score-notification"},
        )

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "POST",
            "https://datamailer.example.com/api/recipient-lists/ml-zoomcamp-2026:@e:@homework:homework-1/transactional-send",
            json={"template_key": "homework-score-notification"},
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_transient_recipient_list_transactional_send_uses_expected_endpoint(
        self,
    ):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        payload = {
            "template_key": "deadline-reminder",
            "members": [{"email": "learner@example.com"}],
        }
        result = client.send_transient_recipient_list_transactional(payload)

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "POST",
            "https://datamailer.example.com/api/transient-recipient-lists/transactional-send",
            json=payload,
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS)
    def test_contact_payload_includes_course_subscription_data(self):
        user = CustomUser.objects.create(
            email="Student@Example.com",
            username="student",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

        payload = contact_payload_for_user(user, course=course)

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
        "course_management.datamailer.DatamailerClient.upsert_contact"
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
        "course_management.datamailer.DatamailerClient.upsert_contact"
    )
    def test_sync_contact_can_be_strict(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        with self.assertRaises(requests.RequestException):
            sync_contact(user)

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_FROM_EMAIL="")
    @patch(
        "course_management.datamailer.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_uses_datamailer_client(
        self, send
    ):
        send.return_value = {"id": "message-id"}

        result = send_transactional_email(
            {
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

        self.assertEqual(result, {"id": "message-id"})
        send.assert_called_once_with(
            {
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_transactional"
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
        "course_management.datamailer.DatamailerClient.send_transactional"
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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.contact_status"
    )
    def test_get_contact_status_uses_datamailer_client(
        self, contact_status
    ):
        contact_status.return_value = {"exists": True}

        result = get_contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        contact_status.assert_called_once_with("student@example.com")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.contact_history"
    )
    def test_get_contact_history_uses_datamailer_client(
        self, contact_history
    ):
        contact_history.return_value = {"transactional_messages": []}

        result = get_contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.get_contact_history")
    @patch("course_management.datamailer.get_contact_status")
    def test_get_email_status_combines_status_and_history(
        self,
        contact_status,
        contact_history,
    ):
        contact_status.return_value = {
            "contact_id": 42,
            "email": "student@example.com",
        }
        contact_history.return_value = {"transactional_messages": []}

        result = get_email_status("student@example.com", limit=5)

        self.assertEqual(
            result,
            {
                "status": {
                    "contact_id": 42,
                    "email": "student@example.com",
                },
                "history": {"transactional_messages": []},
            },
        )
        contact_status.assert_called_once_with("student@example.com")
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.contact_preferences"
    )
    def test_get_email_preferences_for_user_reads_datamailer_categories(
        self,
        contact_preferences,
    ):
        contact_preferences.return_value = {
            "categories": [
                {"tag": "submission-results", "enabled": False},
                {"tag": "deadline-reminders", "enabled": True},
                {"tag": "course-updates", "enabled": False},
            ]
        }
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )

        result = get_email_preferences_for_user(user)

        self.assertEqual(
            result,
            {
                "email_submission_confirmations": False,
                "email_deadline_reminders": True,
                "email_course_updates": False,
            },
        )
        contact_preferences.assert_called_once_with(
            "student@example.com",
            category_tags=[
                "submission-results",
                "deadline-reminders",
                "course-updates",
            ],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.update_contact_preferences"
    )
    def test_update_email_preferences_for_user_writes_datamailer_categories(
        self,
        update_contact_preferences,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )

        result = update_email_preferences_for_user(
            user,
            {
                "email_submission_confirmations": False,
                "email_course_updates": True,
            },
        )

        self.assertTrue(result)
        update_contact_preferences.assert_called_once_with(
            "student@example.com",
            [
                {
                    "tag": "submission-results",
                    "label": "Homework and project submissions",
                    "enabled": False,
                },
                {
                    "tag": "course-updates",
                    "label": "General course-related emails",
                    "enabled": True,
                },
            ],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.transactional_message_status"
    )
    def test_get_transactional_message_status_uses_datamailer_client(
        self,
        message_status,
    ):
        message_status.return_value = {"message": {"id": 42}}

        result = get_transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        message_status.assert_called_once_with(42)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_contact"
    )
    def test_sync_registration_adds_contact_and_registrant_member(
        self,
        upsert_contact,
        upsert_member,
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
        registration = CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
            email="Student@Example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        sync_registration_to_datamailer(registration)

        upsert_contact.assert_called_once()
        self.assertEqual(
            upsert_contact.call_args.args[0]["tags"],
            ["course-ml-zoomcamp", "course-cohort-ml-zoomcamp-2026"],
        )
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

        list_key, source_object_key, payload = (
            enrollment_recipient_list_payload(enrollment)
        )

        self.assertEqual(list_key, course_enrolled_list_key(course))
        self.assertEqual(source_object_key, f"user:{user.pk}")
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
        "course_management.datamailer.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_contact"
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
        "course_management.datamailer.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_contact"
    )
    def test_sync_homework_submission_adds_submitter_member(
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
            student=user, course=course
        )
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

        sync_homework_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            homework_submitters_list_key(homework),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"homework-submission:{submission.pk}",
        )
        self.assertEqual(
            upsert_member.call_args.args[2]["list"]["type"],
            "homework_submitters",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.upsert_contact"
    )
    def test_sync_project_submission_adds_submitter_member(
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
            student=user, course=course
        )
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
            commit_id="a" * 40,
        )

        sync_project_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            project_submitters_list_key(project),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"project-submission:{submission.pk}",
        )
        self.assertEqual(
            upsert_member.call_args.args[2]["list"]["type"],
            "project_submitters",
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_homework_score_notification_payload_targets_homework_submitters(
        self,
    ):
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
        user = CustomUser.objects.create_user(
            username="learner@example.com",
            email="learner@example.com",
            password="test",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
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
        self.assertEqual(
            payload["template_key"],
            "homework-score-notification",
        )
        self.assertEqual(
            payload["idempotency_key"],
            "homework-score:ml-zoomcamp-2026:homework-1",
        )
        self.assertEqual(payload["from_email"], "courses")
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )
        self.assertEqual(
            payload["context"]["profile_url"],
            "https://courses.example.com/accounts/settings/",
        )
        self.assertIn(
            "you submitted Homework 1",
            payload["context"]["notification_footer"],
        )
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_submission_confirmations",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertNotIn("member_sync", payload)
        self.assertNotIn("remove_absent_members", payload)
        self.assertEqual(
            payload["list"]["type"],
            "homework_submitters",
        )
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
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

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_payload_dedupes_student_submissions(
        self,
    ):
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
        user = CustomUser.objects.create_user(
            username="learner@example.com",
            email="learner@example.com",
            password="test",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        older = timezone.now() - timedelta(days=1)
        newer = timezone.now()
        Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
            submitted_at=older,
            total_score=4,
        )
        latest_submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
            submitted_at=newer,
            total_score=9,
        )

        _, payload = homework_score_notification_payload(homework)

        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(
            member["source_object_key"],
            f"homework-submission:{latest_submission.pk}",
        )
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 9)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_skips_opted_out_students(self):
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
        user = CustomUser.objects.create_user(
            username="learner@example.com",
            email="learner@example.com",
            password="test",
            email_submission_confirmations=False,
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
            total_score=9,
        )

        _, payload = homework_score_notification_payload(homework)

        self.assertEqual(payload["members"], [])

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_homework_score_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {"enqueued_count": 1}
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

        self.assertEqual(result, {"enqueued_count": 1})
        bulk_upsert.assert_called_once()
        send_list.assert_called_once()
        self.assertEqual(
            send_list.call_args.args[0],
            homework_submitters_list_key(homework),
        )
        self.assertNotIn("members", send_list.call_args.args[1])
        self.assertNotIn("list", send_list.call_args.args[1])

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_project_score_notification_payload_targets_project_submitters(
        self,
    ):
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
        submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/project",
            commit_id="abc123",
            project_score=70,
            project_learning_in_public_score=5,
            project_faq_score=1,
            peer_review_score=18,
            peer_review_learning_in_public_score=4,
            total_score=98,
            reviewed_enough_peers=True,
            passed=True,
        )

        list_key, payload = project_score_notification_payload(project)

        self.assertEqual(list_key, project_submitters_list_key(project))
        self.assertEqual(
            payload["template_key"],
            "project-score-notification",
        )
        self.assertEqual(
            payload["idempotency_key"],
            "project-score:ml-zoomcamp-2026:project-1",
        )
        self.assertEqual(payload["from_email"], "courses")
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
        self.assertEqual(
            payload["context"]["profile_url"],
            "https://courses.example.com/accounts/settings/",
        )
        self.assertIn(
            "you submitted Project 1",
            payload["context"]["notification_footer"],
        )
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_submission_confirmations",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertNotIn("member_sync", payload)
        self.assertNotIn("remove_absent_members", payload)
        self.assertEqual(payload["list"]["type"], "project_submitters")
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
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

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_dedupes_student_submissions(self):
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
        enrollment = Enrollment.objects.create(student=user, course=course)
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/old",
            submitted_at=timezone.now() - timedelta(days=1),
            total_score=40,
        )
        latest = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/new",
            submitted_at=timezone.now(),
            total_score=90,
        )

        _, payload = project_score_notification_payload(project)

        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{latest.pk}",
        )
        self.assertEqual(member["metadata"]["total_score"], 90)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_peer_review_assignment_payload_includes_links_and_deadline(self):
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        project = Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            state=ProjectState.PEER_REVIEWING.value,
            number_of_peers_to_evaluate=3,
            submission_due_date="2026-01-01T00:00:00Z",
            # Summer instant: PT 15:00, Berlin 00:00 next day.
            peer_review_due_date="2026-07-02T22:00:00Z",
        )

        submissions = []
        for i in range(4):
            user = CustomUser.objects.create_user(
                username=f"learner-{i}@example.com",
                email=f"learner-{i}@example.com",
                password="test",
            )
            if i == 0:
                user.preferred_timezone = "Europe/Berlin"
                user.save(update_fields=["preferred_timezone"])
            enrollment = Enrollment.objects.create(
                student=user, course=course
            )
            submissions.append(
                ProjectSubmission.objects.create(
                    project=project,
                    student=user,
                    enrollment=enrollment,
                    github_link=f"https://github.com/example/p{i}",
                )
            )

        reviewer = submissions[0]
        targets = submissions[1:]
        for target in targets:
            PeerReview.objects.create(
                reviewer=reviewer,
                submission_under_evaluation=target,
                note_to_peer="",
                optional=False,
            )
        # An optional (volunteer) review must not appear in the email.
        PeerReview.objects.create(
            reviewer=reviewer,
            submission_under_evaluation=targets[0],
            note_to_peer="",
            optional=True,
        )

        # Reload so the deadline is a real datetime (not the literal string).
        project.refresh_from_db()
        list_key, payload = peer_review_assignment_notification_payload(
            project
        )

        self.assertEqual(list_key, project_submitters_list_key(project))
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
        # Shared context remains a UTC fallback.
        self.assertEqual(context["deadline_weekday"], "Thursday")
        self.assertEqual(context["deadline_time"], "22:00")
        self.assertEqual(
            context["deadline_summary"], "Thursday, 2 July 2026, 22:00 UTC"
        )

        members_by_email = {m["email"]: m for m in payload["members"]}
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
        # Only the 3 non-optional assignments.
        self.assertEqual(reviewer_member["metadata"]["assigned_reviews_count"], 3)
        self.assertEqual(len(assigned), 3)
        for item in assigned:
            self.assertIn(
                f"/ml-zoomcamp-2026/project/project-1/eval/{item['review_id']}",
                item["eval_url"],
            )
            self.assertTrue(item["eval_url"].startswith("https://"))

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_skips_opted_out_students(self):
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
            email_submission_confirmations=False,
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

        self.assertEqual(payload["members"], [])

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_project_score_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {"enqueued_count": 1}
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

        result = send_project_score_notification(project)

        self.assertEqual(result, {"enqueued_count": 1})
        bulk_upsert.assert_called_once()
        send_list.assert_called_once()
        self.assertEqual(
            send_list.call_args.args[0],
            project_submitters_list_key(project),
        )
        self.assertNotIn("members", send_list.call_args.args[1])
        self.assertNotIn("list", send_list.call_args.args[1])

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_certificate_availability_notification_payload(self):
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
            certificate_url="/certificates/student.pdf",
        )

        payload = certificate_availability_notification_payload(
            enrollment
        )

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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_transactional"
    )
    def test_certificate_availability_notification_respects_course_updates_preference(
        self,
        send,
    ):
        user = CustomUser.objects.create(
            email="student@example.com",
            username="student",
            email_course_updates=False,
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

        payload = certificate_availability_notification_payload(
            enrollment
        )
        result = send_certificate_availability_notification(enrollment)

        self.assertIsNone(payload)
        self.assertIsNone(result)
        send.assert_not_called()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_transactional"
    )
    def test_send_certificate_availability_notification_uses_transactional_send(
        self,
        send,
    ):
        send.return_value = {"id": 123}
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
            certificate_url="/certificates/student.pdf",
        )

        result = send_certificate_availability_notification(enrollment)

        self.assertEqual(result, {"id": 123})
        send.assert_called_once()
        payload = send.call_args.args[0]
        self.assertEqual(
            payload["template_key"],
            "certificate-availability-notification",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_bulk_upserts_registrations(
        self,
        bulk_upsert,
    ):
        bulk_upsert.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }
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
        registration = CourseRegistration.objects.create(
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
            "--course-slug",
            course.slug,
            stdout=out,
        )

        bulk_upsert.assert_called_once()
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            registration_list_key(registration),
        )
        payload = bulk_upsert.call_args.args[1]
        self.assertEqual(payload["list"]["type"], "registrants")
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            f"registration:{registration.pk}",
        )
        self.assertIn(
            "Prepared 1 recipient list(s), 1 member(s).", out.getvalue()
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_recipient_list_backfill_command_bulk_upserts_enrollments(
        self,
        bulk_upsert,
    ):
        bulk_upsert.return_value = {
            "recipient_list": {
                "active_member_count": 1,
            },
        }
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

        out = StringIO()
        call_command(
            "sync_datamailer_recipient_lists",
            "enrollments",
            "--course-slug",
            course.slug,
            stdout=out,
        )

        bulk_upsert.assert_called_once()
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            course_enrolled_list_key(course),
        )
        payload = bulk_upsert.call_args.args[1]
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            f"user:{enrollment.student_id}",
        )
        self.assertIn(
            "Prepared 1 recipient list(s), 1 member(s).", out.getvalue()
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.bulk_upsert_recipient_list_members"
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


class DatamailerSignalTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.sync_contact")
    def test_new_user_syncs_after_commit(self, sync):
        with self.captureOnCommitCallbacks(execute=True):
            user = CustomUser.objects.create(
                email="student@example.com"
            )

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
