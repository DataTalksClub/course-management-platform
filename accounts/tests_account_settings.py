from unittest.mock import patch

from django.urls import reverse

from accounts.tests_account_settings_base import AccountSettingsViewTestBase


class AccountSettingsAuthViewTestCase(AccountSettingsViewTestBase):
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


class AccountSettingsOverviewViewTestCase(AccountSettingsViewTestBase):
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


class AccountSettingsProfileViewTestCase(AccountSettingsViewTestBase):
    def test_account_settings_updates_profile(self):
        self.client.force_login(self.user)
        account_settings_url = reverse("account_settings")
        payload = self.account_settings_profile_payload()

        response = self.client.post(account_settings_url, payload)

        self.assertRedirects(response, account_settings_url)
        self.assert_profile_update_saved()

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
