from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from accounts.tests_base import (
    DATAMAILER_DISABLED_SETTINGS,
    AccountCourseTestCase,
)


@override_settings(**DATAMAILER_DISABLED_SETTINGS)
class AccountSettingsViewTestCase(AccountCourseTestCase):
    def account_settings_profile_payload(self):
        payload = {
            "certificate_name": "Student Certificate",
            "preferred_timezone": "Europe/Berlin",
            "github_url": "https://github.com/student",
            "linkedin_url": "https://linkedin.com/in/student",
            "personal_website_url": "https://student.example.com",
            "about_me": "Learning data.",
            "dark_mode": "on",
        }
        return payload

    def assert_profile_update_saved(self):
        self.user.refresh_from_db()
        self.assertEqual(self.user.certificate_name, "Student Certificate")
        self.assertEqual(self.user.preferred_timezone, "Europe/Berlin")
        self.assertEqual(self.user.github_url, "https://github.com/student")
        self.assertEqual(
            self.user.linkedin_url,
            "https://linkedin.com/in/student",
        )
        self.assertEqual(
            self.user.personal_website_url,
            "https://student.example.com",
        )
        self.assertEqual(self.user.about_me, "Learning data.")
        self.assertFalse(self.user.dark_mode)

    def test_account_settings_requires_login(self):
        account_settings_url = reverse("account_settings")
        login_url = reverse("login")
        expected_redirect_url = (
            f"{login_url}?next={account_settings_url}"
        )

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 302)
        is_expected_redirect = response.url.startswith(expected_redirect_url)
        self.assertTrue(is_expected_redirect)

    def test_account_settings_shows_user_and_enrolled_courses(self):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")
        cadmin_course_list_url = reverse("cadmin_course_list")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "Data Course")
        self.assertContains(response, "Student One")
        self.assertNotContains(response, cadmin_course_list_url)

    def test_account_menu_shows_cadmin_for_staff(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")
        cadmin_course_list_url = reverse("cadmin_course_list")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cadmin_course_list_url)
        self.assertContains(response, "Course admin")

    def test_account_settings_updates_profile(self):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")
        payload = self.account_settings_profile_payload()

        response = self.client.post(account_settings_url, payload)

        self.assertRedirects(response, account_settings_url)
        self.assert_profile_update_saved()

    @patch(
        "accounts.views.email_preferences."
        "get_email_preferences_for_user"
    )
    def test_account_settings_does_not_block_on_datamailer_preferences(
        self,
        get_email_preferences,
    ):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        get_email_preferences.assert_not_called()
        self.assertNotIn(
            "email_submission_confirmations",
            response.context["form"].fields,
        )

    def test_account_settings_profile_save_preserves_dark_mode_toggle(self):
        self.user.dark_mode = True
        self.user.save(update_fields=["dark_mode"])
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")
        payload = {
            "certificate_name": "Student Certificate",
            "github_url": "",
            "linkedin_url": "",
            "personal_website_url": "",
            "about_me": "",
        }

        response = self.client.post(account_settings_url, payload)

        self.assertRedirects(response, account_settings_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

    def test_account_settings_shows_timezone_preference(self):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Display preferences")
        self.assertContains(response, "Deadlines and notification emails")
        self.assertContains(response, "Save display preferences")
        self.assertContains(response, "Europe/Berlin")

    def test_account_settings_shows_browser_timezone_cookie_fallback(self):
        self.client.force_login(self.user)
        self.client.cookies["browser_timezone"] = "Europe%2FBerlin"
        account_settings_url = reverse("account_settings")

        response = self.client.get(account_settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Using browser timezone")
        self.assertContains(response, "Europe/Berlin")
