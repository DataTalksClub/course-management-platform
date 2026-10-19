from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from allauth.account.models import EmailAddress
from allauth.account.views import SignupView
from allauth.core.exceptions import ImmediateHttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.auth import (
    AccountAdapter,
    ConsolidatingSocialAccountAdapter,
    extract_email,
)
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
    def test_signup_get_redirects_to_login(self):
        response = self.client.get("/accounts/signup/")
        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )

    def test_signup_get_preserves_next_param(self):
        response = self.client.get(
            "/accounts/signup/?next=/register/ai-dev-tools/"
        )
        self.assertRedirects(
            response,
            f"{reverse('login')}?next=/register/ai-dev-tools/",
            fetch_redirect_response=False,
        )

    def test_signup_next_with_query_params_survives_intact(self):
        response = self.client.get(
            "/accounts/signup/",
            {"next": "/courses/?page=2&q=1"},
        )

        self.assertEqual(response.status_code, 302)
        query = urlsplit(response["Location"]).query
        self.assertEqual(
            parse_qs(query)["next"],
            ["/courses/?page=2&q=1"],
        )

    def test_signup_next_absolute_url_is_dropped(self):
        response = self.client.get(
            "/accounts/signup/?next=https://evil.example.com/courses/"
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("next", urlsplit(response["Location"]).query)

    def test_signup_next_protocol_relative_url_is_dropped(self):
        response = self.client.get("/accounts/signup/?next=//evil.example.com")

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("next", urlsplit(response["Location"]).query)

    def test_signup_next_javascript_scheme_is_dropped(self):
        response = self.client.get(
            "/accounts/signup/?next=javascript:alert(1)"
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("next", urlsplit(response["Location"]).query)

    def test_signup_post_next_absolute_url_is_dropped(self):
        response = self.client.post(
            "/accounts/signup/",
            {"next": "https://evil.example.com/courses/"},
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("next", urlsplit(response["Location"]).query)

    def test_signup_post_redirects_to_login_and_creates_no_user(self):
        # A user already exists with empty username (as observed in production)
        CustomUser.objects.create(
            username="",
            email="existing@example.com",
        )
        initial_user_count = CustomUser.objects.count()

        # A new user attempts to submit /accounts/signup/
        response = self.client.post(
            "/accounts/signup/",
            {
                "email": "newuser@example.com",
                "password1": "Password123!",
                "password2": "Password123!",
            },
        )

        # The endpoint should redirect cleanly without 500 and without creating a user
        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertEqual(CustomUser.objects.count(), initial_user_count)
        self.assertFalse(
            CustomUser.objects.filter(email="newuser@example.com").exists()
        )

    def test_allauth_fallback_signup_view_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.sessions.middleware import SessionMiddleware

        factory = RequestFactory()
        request = factory.post(
            "/accounts/signup/",
            {
                "email": "fallback@example.com",
                "password1": "Password123!",
                "password2": "Password123!",
            },
        )
        request.user = AnonymousUser()
        SessionMiddleware(lambda req: None).process_request(request)
        response = SignupView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertFalse(
            CustomUser.objects.filter(email="fallback@example.com").exists()
        )

    def test_socialaccount_adapter_remains_open_for_signup(self):
        adapter = ConsolidatingSocialAccountAdapter()
        self.assertTrue(adapter.is_open_for_signup(None, None))

    def test_account_adapter_closed_for_signup(self):
        adapter = AccountAdapter()
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(None)
        self.assertEqual(ctx.exception.response.status_code, 302)
        self.assertEqual(ctx.exception.response.url, reverse("login"))

    def test_custom_user_save_defaults_username_to_email(self):
        user = CustomUser(email="testuser@example.com")
        user.save()
        self.assertEqual(user.username, "testuser@example.com")



