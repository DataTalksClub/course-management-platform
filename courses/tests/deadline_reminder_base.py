from datetime import datetime, timezone as datetime_timezone

from django.core.management import call_command
from django.test import TestCase

from accounts.models import CustomUser
from courses.models import Course, Enrollment


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DeadlineReminderTestBase(TestCase):
    def reminder_run_time(self):
        return datetime(2026, 6, 16, 9, tzinfo=datetime_timezone.utc)

    def create_user(
        self,
        username,
        email,
        *,
        preferred_timezone="",
    ):
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password="password",
        )
        user.preferred_timezone = preferred_timezone
        user.save(update_fields=["preferred_timezone"])
        return user

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

    def create_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def run_deadline_reminders(self, now, stdout=None, dry_run=False):
        args = ["send_deadline_reminders", "--now", now.isoformat()]
        if dry_run:
            args.append("--dry-run")
        call_command(*args, stdout=stdout)

    def members_by_email(self, payload):
        members_by_email = {}
        members = payload["members"]
        for member in members:
            email = member["email"]
            members_by_email[email] = member
        return members_by_email
