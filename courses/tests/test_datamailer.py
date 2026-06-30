from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import Mock, patch
from io import StringIO

import requests
from django.core.management import call_command
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
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
    registration_list_key,
)
from course_management.datamailer.payloads import (
    certificate_availability_notification_payload,
    course_graduate_recipient_list_payload,
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
