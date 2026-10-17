from types import SimpleNamespace
from unittest.mock import Mock

from allauth.account.models import EmailAddress
from django.test import TestCase

from accounts.auth import ConsolidatingSocialAccountAdapter, extract_email
from accounts.models import CustomUser


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


class ConsolidatingSocialAccountAdapterTestCase(TestCase):
    def test_social_login_connects_existing_user_without_email_address(self):
        email = "alexey@datatalks.club"
        user = CustomUser.objects.create_user(
            username=email,
            email="",
        )
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(extra_data={"email": email}),
            is_existing=False,
            email_addresses=[],
            connect=Mock(),
        )
        adapter = ConsolidatingSocialAccountAdapter()

        adapter.pre_social_login(None, sociallogin)

        sociallogin.connect.assert_called_once_with(None, user)
        user.refresh_from_db()
        self.assertEqual(user.email, email)
        email_address = EmailAddress.objects.get(user=user)
        self.assertEqual(email_address.email, email)
        self.assertTrue(email_address.primary)
        self.assertTrue(email_address.verified)


class SignupRouteTestCase(TestCase):
    def test_signup_get_renders_social_login(self):
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_signup_post_does_not_500_with_duplicate_empty_username(self):
        # A user already exists with empty username (as observed in production)
        CustomUser.objects.create(
            username="",
            email="existing@example.com",
        )

        # A new user attempts to submit /accounts/signup/
        response = self.client.post(
            "/accounts/signup/",
            {
                "email": "newuser@example.com",
                "password1": "Password123!",
                "password2": "Password123!",
            },
        )

        # The endpoint should not crash with a 500 Internal Server Error
        self.assertNotEqual(response.status_code, 500)

    def test_custom_user_save_defaults_username_to_email(self):
        user = CustomUser(email="testuser@example.com")
        user.save()
        self.assertEqual(user.username, "testuser@example.com")



