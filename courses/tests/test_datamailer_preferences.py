from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.preferences import (
    get_email_preferences_for_user,
    update_email_preferences_for_user,
)

from .datamailer_settings import DATAMAILER_SETTINGS


class DatamailerPreferencesTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.update_contact_preferences"
    )
    def test_update_email_preferences_for_user_writes_datamailer_categories(
        self,
        update_contact_preferences,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )
        updated_preferences = {
            "email_submission_confirmations": False,
            "email_course_updates": True,
        }

        result = update_email_preferences_for_user(
            user,
            updated_preferences,
        )

        self.assertTrue(result)
        expected_updates = []
        submission_preference = {
            "tag": "submission-results",
            "label": "Homework and project submissions",
            "enabled": False,
        }
        expected_updates.append(submission_preference)
        course_preference = {
            "tag": "course-updates",
            "label": "General course-related emails",
            "enabled": True,
        }
        expected_updates.append(course_preference)
        update_contact_preferences.assert_called_once_with(
            "student@example.com",
            expected_updates,
        )
