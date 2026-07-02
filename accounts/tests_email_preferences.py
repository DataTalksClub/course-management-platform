from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from accounts.models import CustomUser
from accounts.tests_base import (
    DATAMAILER_DISABLED_SETTINGS,
    AccountCourseTestCase,
)


@override_settings(**DATAMAILER_DISABLED_SETTINGS)
class AccountEmailPreferencesTestCase(AccountCourseTestCase):
    @patch(
        "accounts.views.email_preferences."
        "update_email_preferences_for_user"
    )
    def test_account_email_preferences_update_proxies_to_datamailer(
        self,
        update_email_preferences,
    ):
        update_email_preferences.return_value = True
        self.client.force_login(self.user)
        url = reverse("account_email_preferences")
        payload = {"field": "email_deadline_reminders", "value": "false"}

        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(
            response_data,
            {
                "field": "email_deadline_reminders",
                "value": False,
                "datamailer_synced": True,
            },
        )
        update_email_preferences.assert_called_once_with(
            self.user,
            {"email_deadline_reminders": False},
        )

    @patch(
        "accounts.views.email_preferences."
        "get_email_preferences_for_user"
    )
    def test_account_email_preferences_read_proxies_to_datamailer(
        self,
        get_email_preferences,
    ):
        get_email_preferences.return_value = {
            "email_submission_confirmations": False,
            "email_deadline_reminders": True,
            "email_course_updates": False,
        }
        self.client.force_login(self.user)
        url = reverse("account_email_preferences")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(
            response_data,
            {
                "preferences": {
                    "email_submission_confirmations": False,
                    "email_deadline_reminders": True,
                    "email_course_updates": False,
                },
            },
        )
        get_email_preferences.assert_called_once_with(self.user)

    def test_account_email_preferences_unavailable_returns_503(self):
        self.client.force_login(self.user)
        url = reverse("account_email_preferences")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)

    def test_custom_user_does_not_store_email_preference_fields(self):
        field_names = set()
        for field in CustomUser._meta.get_fields():
            field_names.add(field.name)

        self.assertNotIn("email_submission_confirmations", field_names)
        self.assertNotIn("email_deadline_reminders", field_names)
        self.assertNotIn("email_course_updates", field_names)

    def test_account_settings_shows_email_preference_categories(self):
        self.client.force_login(self.user)
        url = reverse("account_settings")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Homework and project submissions",
        )
        self.assertContains(
            response,
            "Sends confirmation and score emails",
        )
        self.assertContains(response, "Deadline reminders")
        self.assertContains(response, "within 24 hours")
        self.assertContains(response, "one week before the deadline")
        self.assertContains(response, "one day before the deadline")
        self.assertContains(response, "links to unfinished reviews")
        self.assertContains(response, "mandatory for project completion")
        self.assertContains(response, "General course-related emails")
        self.assertContains(response, "course start announcements")
