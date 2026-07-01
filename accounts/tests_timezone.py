import json

from django.test import override_settings
from django.urls import reverse

from accounts.tests_base import (
    DATAMAILER_DISABLED_SETTINGS,
    AccountCourseTestCase,
)


@override_settings(**DATAMAILER_DISABLED_SETTINGS)
class AccountTimezonePreferenceTestCase(AccountCourseTestCase):
    def post_timezone_preference(self, payload):
        request_body = json.dumps(payload)
        response = self.client.post(
            reverse("update_timezone_preference"),
            data=request_body,
            content_type="application/json",
        )
        return response

    def test_update_timezone_preference_passive_detects_browser_timezone(self):
        self.client.force_login(self.user)
        payload = {"timezone": "Europe/Berlin", "passive": True}

        response = self.post_timezone_preference(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_timezone, "Europe/Berlin")

    def test_update_timezone_preference_passive_does_not_override_saved(self):
        self.user.preferred_timezone = "America/New_York"
        self.user.save(update_fields=["preferred_timezone"])
        self.client.force_login(self.user)
        payload = {"timezone": "Europe/Berlin", "passive": True}

        response = self.post_timezone_preference(payload)

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_timezone, "America/New_York")

    def test_update_timezone_preference_rejects_invalid_timezone(self):
        self.client.force_login(self.user)
        payload = {"timezone": "Mars/Olympus"}

        response = self.post_timezone_preference(payload)

        self.assertEqual(response.status_code, 400)

    def test_update_timezone_preference_requires_timezone_field(self):
        self.client.force_login(self.user)
        payload = {}

        response = self.post_timezone_preference(payload)

        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error, "timezone field is required")

    def test_update_timezone_preference_rejects_non_string_timezone(self):
        self.client.force_login(self.user)
        payload = {"timezone": 10}

        response = self.post_timezone_preference(payload)

        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error, "timezone must be a string")
