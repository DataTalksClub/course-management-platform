from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import project_submitters_list_key
from course_management.datamailer.payloads import (
    peer_review_assignment_notification_payload,
)
from course_management.datamailer.sync import (
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


class DatamailerPeerReviewTest(TestCase):
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
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

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

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

    def create_peer_review_assignment_fixture(self):
        project = self.create_project(
            state=ProjectState.PEER_REVIEWING.value,
            number_of_peers_to_evaluate=3,
            # Summer instant: PT 15:00, Berlin 00:00 next day.
            peer_review_due_date="2026-07-02T22:00:00Z",
        )
        submissions = []
        for index in range(4):
            user = self.create_user(f"learner-{index}@example.com")
            if index == 0:
                user.preferred_timezone = "Europe/Berlin"
                user.save(update_fields=["preferred_timezone"])
            submission = self.create_project_submission(
                project,
                user,
                github_link=f"https://github.com/example/p{index}",
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

    def assert_peer_review_send_audit(self):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.RECIPIENT_LIST)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.event, "peer_review_assignment")
        self.assertEqual(audit.intended_count, 4)
        self.assertEqual(audit.enqueued_count, 4)

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
        self.assert_peer_review_send_audit()
