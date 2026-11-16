import json
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from courses.models import Course, CourseRegistration, RegistrationCampaign


class ChangeRegistrationEmailCommandTests(TestCase):
    def setUp(self):
        course = Course.objects.create(slug="c", title="C")
        campaign = RegistrationCampaign.objects.create(
            slug="camp", title="Camp", current_course=course)
        self.reg = CourseRegistration.objects.create(
            campaign=campaign, course=course, email="a@example.com")
        self.other = CourseRegistration.objects.create(
            campaign=campaign, course=course, email="b@example.com")

    def run_cmd(self, *args):
        out = StringIO()
        call_command("change_registration_email", *args, stdout=out)
        return json.loads(out.getvalue())

    def test_dry_run_then_apply(self):
        self.assertFalse(
            self.run_cmd(self.reg.pk, "n@example.com")["applied"])
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "a@example.com")
        self.run_cmd(self.reg.pk, "N@example.com", "--apply")
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "n@example.com")
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_rejected(self):
        with self.assertRaises(CommandError):
            self.run_cmd(self.reg.pk, "b@example.com", "--apply")
