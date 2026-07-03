from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from accounts.models import CustomUser
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import project_submitters_list_key
from course_management.datamailer.payloads.peer_review import (
    peer_review_assignment_notification_payload,
)
from course_management.datamailer.sync.peer_review_notifications import (
    send_peer_review_assignment_notification,
)
from courses.models import (
    Course,
    Enrollment,
    PeerReview,
    Project,
    ProjectState,
    ProjectSubmission,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


def create_ml_course():
    return Course.objects.create(
        slug="ml-zoomcamp-2026",
        title="ML Zoomcamp 2026",
        description="Machine learning",
    )


def create_project(course=None, **overrides):
    defaults = {
        "course": course or create_ml_course(),
        "slug": "project-1",
        "title": "Project 1",
        "submission_due_date": "2026-01-01T00:00:00Z",
        "peer_review_due_date": "2026-01-08T00:00:00Z",
    }
    defaults.update(overrides)
    return Project.objects.create(**defaults)


def create_user(email):
    return CustomUser.objects.create_user(
        username=email,
        email=email,
        password="test",
    )


def create_enrollment(user, course):
    return Enrollment.objects.create(student=user, course=course)


def create_project_submission(project, user, **overrides):
    enrollment = create_enrollment(user, project.course)
    defaults = {
        "project": project,
        "student": user,
        "enrollment": enrollment,
        "github_link": "https://github.com/example/project",
        "commit_id": "abc123",
    }
    defaults.update(overrides)
    return ProjectSubmission.objects.create(**defaults)


def create_peer_review_assignment_project():
    return create_project(
        state=ProjectState.PEER_REVIEWING.value,
        number_of_peers_to_evaluate=3,
        # Summer instant: PT 15:00, Berlin 00:00 next day.
        peer_review_due_date="2026-07-02T22:00:00Z",
    )


def create_peer_review_assignment_submission(project, index):
    user = create_user(f"learner-{index}@example.com")
    if index == 0:
        user.preferred_timezone = "Europe/Berlin"
        user.save(update_fields=["preferred_timezone"])
    return create_project_submission(
        project,
        user,
        github_link=f"https://github.com/example/p{index}",
    )


def create_peer_review_assignment_submissions(project):
    submissions = []
    for index in range(4):
        submission = create_peer_review_assignment_submission(
            project,
            index,
        )
        submissions.append(submission)
    return submissions


def create_peer_review_assignment(reviewer, target, optional):
    PeerReview.objects.create(
        reviewer=reviewer,
        submission_under_evaluation=target,
        note_to_peer="",
        optional=optional,
    )


def create_reviewer_assignments(submissions):
    reviewer = submissions[0]
    targets = submissions[1:]
    for target in targets:
        create_peer_review_assignment(
            reviewer,
            target,
            optional=False,
        )
    create_peer_review_assignment(
        reviewer,
        targets[0],
        optional=True,
    )


def create_peer_review_assignment_fixture():
    project = create_peer_review_assignment_project()
    submissions = create_peer_review_assignment_submissions(project)
    create_reviewer_assignments(submissions)
    project.refresh_from_db()
    return project


def assert_peer_review_assignment_payload(test_case, payload, project):
    test_case.assertEqual(payload["template_key"], "peer-review-assignment")
    test_case.assertEqual(payload["category_tag"], "submission-results")
    test_case.assertEqual(
        payload["idempotency_key"],
        "peer-review-assignment:ml-zoomcamp-2026:project-1",
    )
    test_case.assertEqual(
        payload["metadata"]["event"],
        "peer_review_assignment",
    )
    context = payload["context"]
    test_case.assertEqual(context["number_of_peers_to_evaluate"], 3)
    peer_review_due_at = project.peer_review_due_date.isoformat()
    test_case.assertEqual(
        context["peer_review_due_at"],
        peer_review_due_at,
    )
    test_case.assertEqual(context["deadline_weekday"], "Thursday")
    test_case.assertEqual(context["deadline_time"], "22:00")
    test_case.assertEqual(
        context["deadline_summary"], "Thursday, 2 July 2026, 22:00 UTC"
    )


def assert_berlin_reviewer_assignments(test_case, payload):
    members_by_email = {}
    members = payload["members"]
    for member in members:
        email = member["email"]
        members_by_email[email] = member
    members_by_email_count = len(members_by_email)
    test_case.assertEqual(members_by_email_count, 4)
    reviewer_member = members_by_email["learner-0@example.com"]
    test_case.assertEqual(
        reviewer_member["metadata"]["deadline_summary"],
        "Friday, 3 July 2026, 00:00 Europe/Berlin",
    )
    test_case.assertEqual(
        reviewer_member["metadata"]["deadline_timezone"],
        "Europe/Berlin",
    )
    assigned = reviewer_member["metadata"]["assigned_reviews"]
    test_case.assertEqual(
        reviewer_member["metadata"]["assigned_reviews_count"],
        3,
    )
    assigned_count = len(assigned)
    test_case.assertEqual(assigned_count, 3)
    for item in assigned:
        test_case.assertIn(
            f"/ml-zoomcamp-2026/project/project-1/eval/{item['review_id']}",
            item["eval_url"],
        )
        has_secure_eval_url = item["eval_url"].startswith("https://")
        test_case.assertTrue(has_secure_eval_url)


def assert_peer_review_send_audit(test_case):
    audit = DatamailerSendAudit.objects.get()
    test_case.assertEqual(
        audit.send_type,
        DatamailerSendAuditType.RECIPIENT_LIST,
    )
    test_case.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
    test_case.assertEqual(audit.event, "peer_review_assignment")
    test_case.assertEqual(audit.intended_count, 4)
    test_case.assertEqual(audit.enqueued_count, 4)


class DatamailerPeerReviewPayloadTest(TestCase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
        DATAMAILER_FROM_EMAIL="courses",
    )
    def test_peer_review_assignment_payload_includes_links_and_deadline(self):
        project = create_peer_review_assignment_fixture()
        list_key, payload = peer_review_assignment_notification_payload(
            project
        )

        expected_list_key = project_submitters_list_key(project)
        self.assertEqual(list_key, expected_list_key)
        self.assertEqual(payload["from_email"], "courses")
        assert_peer_review_assignment_payload(self, payload, project)
        assert_berlin_reviewer_assignments(self, payload)


class DatamailerPeerReviewMembersQueryTest(TestCase):
    def _add_submitters(self, project, count):
        for index in range(count):
            user = create_user(f"extra-{index}@example.com")
            create_project_submission(
                project,
                user,
                github_link=f"https://github.com/example/extra{index}",
            )

    def _peerreview_query_count(self, project):
        from course_management.datamailer.payloads.peer_review_members import (  # noqa: E501
            peer_review_assignment_notification_members,
        )

        with CaptureQueriesContext(connection) as ctx:
            peer_review_assignment_notification_members(project)
        return len(
            [
                q
                for q in ctx.captured_queries
                if 'FROM "courses_peerreview"' in q["sql"]
            ]
        )

    def test_reviewers_are_prefetched_not_queried_per_submitter(self):
        """Building the member list must not query reviewers per submitter."""
        project = create_peer_review_assignment_fixture()
        self._add_submitters(project, 20)

        peerreview_queries = self._peerreview_query_count(project)

        # The reviewers relation is prefetched in a single query, so the
        # count stays constant instead of growing with the submitter count.
        self.assertLessEqual(peerreview_queries, 1)


class DatamailerPeerReviewPreviewCommandTest(TestCase):
    @override_settings(PUBLIC_BASE_URL="https://courses.example.com")
    def test_preview_peer_review_email_prints_submission_previews(self):
        project = create_peer_review_assignment_fixture()

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


class DatamailerPeerReviewNotificationSendTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_list"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
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
        project = create_peer_review_assignment_fixture()

        result = send_peer_review_assignment_notification(project)

        self.assertEqual(result["enqueued_count"], 4)
        bulk_upsert.assert_called_once()
        send_list.assert_called_once()
        expected_list_key = project_submitters_list_key(project)
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            expected_list_key,
        )
        bulk_upsert_payload = bulk_upsert.call_args.args[1]
        members_count = len(bulk_upsert_payload["members"])
        self.assertEqual(members_count, 4)
        self.assertEqual(
            send_list.call_args.args[0],
            expected_list_key,
        )
        self.assertNotIn("members", send_list.call_args.args[1])
        self.assertNotIn("list", send_list.call_args.args[1])
        assert_peer_review_send_audit(self)
