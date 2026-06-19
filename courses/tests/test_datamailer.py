from unittest.mock import Mock, patch
from io import StringIO

import requests
from django.core.management import call_command
from django.test import TestCase, override_settings

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
    get_transactional_message_status,
    homework_score_notification_payload,
    homework_submitters_list_key,
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
)
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
            "course-registrants:ml-zoomcamp-2026",
            "registration:42",
            {"email": "student@example.com"},
        )

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "PUT",
            "https://datamailer.example.com/api/recipient-lists/course-registrants:ml-zoomcamp-2026/members/registration:42",
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
            "homework-submitters:ml-zoomcamp-2026:homework-1",
            {"template_key": "homework-score-notification"},
        )

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "POST",
            "https://datamailer.example.com/api/recipient-lists/homework-submitters:ml-zoomcamp-2026:homework-1/transactional-send",
            json={"template_key": "homework-score-notification"},
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

    @override_settings(**DATAMAILER_SETTINGS)
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
            "https://courses.example.com/ml-zoomcamp-2026/",
        )
        self.assertEqual(payload["member_sync"], "reconcile")
        self.assertTrue(payload["remove_absent_members"])
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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    def test_send_homework_score_notification_uses_list_send(
        self,
        send_list,
    ):
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
        send_list.assert_called_once()
        self.assertEqual(
            send_list.call_args.args[0],
            homework_submitters_list_key(homework),
        )

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
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1",
        )
        self.assertEqual(payload["member_sync"], "reconcile")
        self.assertTrue(payload["remove_absent_members"])
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
        self.assertTrue(member["metadata"]["reviewed_enough_peers"])
        self.assertTrue(member["metadata"]["passed"])

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    def test_send_project_score_notification_uses_list_send(
        self,
        send_list,
    ):
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
        send_list.assert_called_once()
        self.assertEqual(
            send_list.call_args.args[0],
            project_submitters_list_key(project),
        )

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
            "course-registrants:ml-zoomcamp-2026: 1 member(s)",
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
