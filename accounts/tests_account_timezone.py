from django.urls import reverse

from accounts.tests_account_settings_base import AccountSettingsViewTestBase


class AccountSettingsTimezoneViewTestCase(AccountSettingsViewTestBase):
    def test_account_settings_shows_timezone_preference(self):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Display preferences")
        self.assertContains(response, "Deadlines and notification emails")
        # The form has a single footer action, not a per-section save.
        self.assertContains(response, "Save changes")
        self.assertContains(response, "Europe/Berlin")

    def test_account_settings_shows_browser_timezone_cookie_fallback(self):
        self.client.force_login(self.user)
        self.client.cookies["browser_timezone"] = "Europe%2FBerlin"
        account_settings_url = reverse("account_settings")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Using browser timezone")
        self.assertContains(response, "Europe/Berlin")
