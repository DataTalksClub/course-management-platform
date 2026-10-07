from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.preferences import (
    get_email_preferences_for_user,
)

from .datamailer_settings import RELAY_SETTINGS


class DatamailerPreferencesTest(TestCase):
    @override_settings(**RELAY_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.contact_preferences"
    )
    def test_get_email_preferences_for_user_reads_datamailer_categories(
        self,
        contact_preferences,
    ):
        categories = []
        submission_category = {
            "tag": "submission-results",
            "enabled": False,
        }
        categories.append(submission_category)
        deadline_category = {
            "tag": "deadline-reminders",
            "enabled": True,
        }
        categories.append(deadline_category)
        course_category = {
            "tag": "course-updates",
            "enabled": False,
        }
        categories.append(course_category)
        contact_preferences.return_value = {"categories": categories}
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )

        result = get_email_preferences_for_user(user)

        expected = {
            "email_submission_confirmations": False,
            "email_deadline_reminders": True,
            "email_course_updates": False,
        }
        self.assertEqual(result, expected)
        category_tags = []
        category_tags.append("submission-results")
        category_tags.append("deadline-reminders")
        category_tags.append("course-updates")
        contact_preferences.assert_called_once_with(
            "student@example.com",
            category_tags=category_tags,
        )
