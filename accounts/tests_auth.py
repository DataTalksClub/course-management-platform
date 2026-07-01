from types import SimpleNamespace

from django.test import TestCase

from accounts.auth import extract_email


class ExtractEmailTestCase(TestCase):
    def email_address(self, email, verified=False):
        return SimpleNamespace(email=email, verified=verified)

    def sociallogin_with_emails(self, *email_addresses):
        email_address_list = list(email_addresses)
        return SimpleNamespace(email_addresses=email_address_list)

    def test_extract_email_prefers_response_email(self):
        verified_email = self.email_address(
            "verified@example.com",
            verified=True,
        )
        sociallogin = self.sociallogin_with_emails(
            verified_email,
        )

        email = extract_email(
            {"email": "response@example.com"},
            sociallogin=sociallogin,
        )

        self.assertEqual(email, "response@example.com")

    def test_extract_email_uses_verified_social_email(self):
        first_email = self.email_address("first@example.com")
        verified_email = self.email_address(
            "verified@example.com",
            verified=True,
        )
        sociallogin = self.sociallogin_with_emails(
            first_email,
            verified_email,
        )

        email = extract_email({}, sociallogin=sociallogin)

        self.assertEqual(email, "verified@example.com")

    def test_extract_email_falls_back_to_first_social_email(self):
        first_email = self.email_address("first@example.com")
        second_email = self.email_address("second@example.com")
        sociallogin = self.sociallogin_with_emails(
            first_email,
            second_email,
        )

        email = extract_email({}, sociallogin=sociallogin)

        self.assertEqual(email, "first@example.com")

    def test_extract_email_falls_back_to_notification_email(self):
        email = extract_email(
            {"notification_email": "notify@example.com"}
        )

        self.assertEqual(email, "notify@example.com")

    def test_extract_email_raises_when_missing(self):
        with self.assertRaises(KeyError):
            extract_email({})
