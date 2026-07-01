from dataclasses import dataclass
from datetime import datetime, timedelta

from courses.models import Course, Project, ProjectState


@dataclass(frozen=True)
class ProjectReminderData:
    course: Course
    now: datetime
    slug: str
    title: str
    submission_delta: timedelta
    state: str


class ProjectSubmissionReminderTestMixin:
    def create_project(self, data):
        return Project.objects.create(
            course=data.course,
            slug=data.slug,
            title=data.title,
            submission_due_date=data.now + data.submission_delta,
            peer_review_due_date=data.now + timedelta(days=10),
            state=data.state,
        )

    def create_project_submission_reminder_fixture(self, now):
        course = self.create_course()
        user = self.create_user("student", "student@example.com")
        opted_out_user = self.create_user(
            "opted-out",
            "opted-out@example.com",
        )
        self.create_enrollment(user, course)
        self.create_enrollment(opted_out_user, course)
        project_week_delta = timedelta(days=8, hours=2)
        project_week = ProjectReminderData(
            course=course,
            now=now,
            slug="project-week",
            title="Project Week",
            submission_delta=project_week_delta,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_project(project_week)
        project_day_delta = timedelta(days=1, hours=14)
        project_day = ProjectReminderData(
            course=course,
            now=now,
            slug="project-day",
            title="Project Day",
            submission_delta=project_day_delta,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_project(project_day)

    def assert_project_reminder_payloads(self, send_transient):
        self.assertEqual(send_transient.call_count, 2)
        send_payloads = self.sent_reminder_payloads(send_transient)
        self.assert_project_reminder_list_keys(send_payloads)
        self.assert_project_reminder_keys(send_payloads)
        self.assert_project_reminder_members(send_payloads)

    def sent_reminder_payloads(self, send_transient):
        send_payloads = []
        send_calls = send_transient.call_args_list
        for call in send_calls:
            payload = call.args[0]
            send_payloads.append(payload)
        return send_payloads

    def assert_project_reminder_list_keys(self, send_payloads):
        list_keys = []
        for payload in send_payloads:
            list_key = payload["list"]["key"]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [
                "deadline-reminders:project-submission:"
                "ml-zoomcamp-2026:project-day:24h",
                "deadline-reminders:project-submission:"
                "ml-zoomcamp-2026:project-week:7d",
            ],
        )

    def assert_project_reminder_keys(self, send_payloads):
        reminder_keys = []
        for payload in send_payloads:
            reminder_key = payload["context"]["reminder_key"]
            reminder_keys.append(reminder_key)
        self.assertEqual(
            reminder_keys,
            ["24h", "7d"],
        )

    def assert_project_reminder_members(self, send_payloads):
        for payload in send_payloads:
            member_emails = set()
            members = payload["members"]
            for member in members:
                email = member["email"]
                member_emails.add(email)
            self.assertEqual(
                member_emails,
                {"student@example.com", "opted-out@example.com"},
            )
