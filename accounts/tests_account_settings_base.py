from django.test import override_settings

from accounts.tests_base import (
    DATAMAILER_DISABLED_SETTINGS,
    AccountCourseTestCase,
)


@override_settings(**DATAMAILER_DISABLED_SETTINGS)
class AccountSettingsViewTestBase(AccountCourseTestCase):
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
