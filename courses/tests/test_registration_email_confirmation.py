"""Tests for double opt-in registration email confirmation.

Covers: typo suggestion, MX checks (incl. null MX, DNS failure
non-blocking), pending -> confirmed transition, token handling
(idempotent, expired, invalid), resend rate limiting, fix-email flow,
backfill migration, and the full register -> pending -> confirm E2E.
"""

from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.email_validation import (
    domain_has_mx,
    email_domain_has_mx,
    suggest_email_correction,
)
from courses.models import CourseRegistration
from courses.registration_confirmation import (
    EMAIL_CONFIRMATION_MAX_RESENDS,
    confirm_registration_by_token,
    management_token,
)
from courses.tests.registration_campaign_base import (
    RegistrationCampaignBase,
)


RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "secret-token",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
}


def _fake_mx(host="mail.example.net.", preference=10):
    class FakeAnswer:
        def __init__(self):
            self.exchange = host
            self.preference = preference

    class FakeAnswers(list):
        pass

    return FakeAnswers([FakeAnswer()])


class TypoSuggestionTests(TestCase):
    def test_common_typos_suggest_correction(self):
        cases = {
            "user@hmail.com": "user@gmail.com",
            "user@gmial.com": "user@gmail.com",
            "user@gmai.com": "user@gmail.com",
            "user@gmail.co": "user@gmail.com",
            "user@gmail.con": "user@gmail.com",
            "user@yahooo.com": "user@yahoo.com",
            "user@hotmial.com": "user@hotmail.com",
            "user@outlok.com": "user@outlook.com",
            "user@gamil.com": "user@gmail.com",
            "user@outlook.con": "user@outlook.com",
        }
        for typed, expected in cases.items():
            with self.subTest(typed=typed):
                self.assertEqual(
                    suggest_email_correction(typed), expected
                )

    def test_correct_domains_have_no_suggestion(self):
        for email in (
            "user@gmail.com",
            "user@yahoo.com",
            "user@outlook.com",
            "user@company.io",
        ):
            with self.subTest(email=email):
                self.assertIsNone(suggest_email_correction(email))

    def test_malformed_addresses_have_no_suggestion(self):
        self.assertIsNone(suggest_email_correction("not-an-email"))
        self.assertIsNone(suggest_email_correction("a@b@c.com"))


class MxCheckTests(TestCase):
    def test_domain_without_mx_returns_false(self):
        import dns.resolver

        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.resolver.NXDOMAIN(),
        ):
            self.assertIs(domain_has_mx("no-mail-here.example"), False)

    def test_null_mx_returns_false(self):
        with patch(
            "courses.email_validation._mx_records_for_domain",
            return_value=_fake_mx(host=".", preference=0),
        ):
            self.assertIs(domain_has_mx("rejects-all.example"), False)

    def test_valid_mx_returns_true(self):
        with patch(
            "courses.email_validation._mx_records_for_domain",
            return_value=_fake_mx(),
        ):
            self.assertTrue(domain_has_mx("goodmail.com"))

    def test_dns_timeout_does_not_block(self):
        import dns.exception

        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.exception.Timeout(),
        ):
            self.assertIsNone(domain_has_mx("flaky-dns.com"))
            self.assertIsNone(email_domain_has_mx("user@flaky-dns.com"))

    def test_dns_failure_does_not_block(self):
        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=Exception("boom"),
        ):
            self.assertIsNone(domain_has_mx("flaky-dns.com"))

    def test_reserved_domains_are_validated_too(self):
        import dns.resolver

        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.resolver.NXDOMAIN(),
        ):
            self.assertIs(domain_has_mx("example.com"), False)
            self.assertIs(domain_has_mx("anything.invalid"), False)


class RegistrationPendingFlowTests(RegistrationCampaignBase):
    @override_settings(**RELAY_SETTINGS)
    @patch("courses.views.registration.sync_registration_to_relay")
    @patch(
        "courses.views.registration.send_registration_confirmation_email"
    )
    def test_register_creates_pending_registration(
        self, send_confirmation, sync_datamailer
    ):
        url = self.campaign_url()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url, self.registration_payload(email="New@Example.com")
            )
        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertFalse(registration.email_confirmed)
        self.assertTrue(registration.email_confirmation_token)
        self.assertIsNotNone(registration.email_confirmation_sent_at)
        self.assertEqual(
            registration.email_confirmation_resend_count, 1
        )
        # Pending page: shows the exact address typed and the must-click
        # instruction, plus fix-email and resend options.
        self.assertContains(response, "Check your inbox")
        self.assertContains(response, "New@Example.com")
        self.assertContains(
            response, "MUST click the confirmation link"
        )
        self.assertContains(response, "Wrong email? Fix it")
        self.assertContains(response, "Resend confirmation email")
        sync_datamailer.assert_called_once_with(registration)
        send_confirmation.assert_called_once_with(registration)

    @override_settings(**RELAY_SETTINGS)
    def test_typo_address_rejected_with_suggestion(self):
        url = self.campaign_url()
        payload = self.registration_payload(email="user@gmial.com")
        with patch(
            "courses.email_validation._mx_records_for_domain",
            return_value=_fake_mx(),
        ):
            response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Did you mean user@gmail.com?")
        self.assertEqual(CourseRegistration.objects.count(), 0)

    @override_settings(**RELAY_SETTINGS)
    def test_domain_without_mx_rejected(self):
        import dns.resolver

        url = self.campaign_url()
        payload = self.registration_payload(email="user@no-mx-here.com")
        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.resolver.NXDOMAIN(),
        ):
            response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not accept mail")
        self.assertEqual(CourseRegistration.objects.count(), 0)

    @override_settings(**RELAY_SETTINGS)
    @patch("courses.views.registration.sync_registration_to_relay")
    @patch(
        "courses.views.registration.send_registration_confirmation_email"
    )
    def test_dns_failure_does_not_block_registration(
        self, send_confirmation, sync_datamailer
    ):
        url = self.campaign_url()
        payload = self.registration_payload(email="user@flaky-dns.com")
        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=Exception("dns down"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)

    def test_duplicate_post_shows_pending_block_with_resend(self):
        # Refresh-after-POST re-submits the same address: the pending
        # confirmation block (with resend/fix options) must survive.
        with (
            patch(
                "courses.views.registration.send_registration_confirmation_email"
            ),
            patch(
                "courses.views.registration.sync_registration_to_relay"
            ),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    self.campaign_url(),
                    self.registration_payload(
                        email="Again@Example.com"
                    ),
                )
        response = self.client.post(
            self.campaign_url(),
            self.registration_payload(email="Again@Example.com"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check your inbox")
        self.assertContains(response, "Again@Example.com")
        self.assertContains(response, "Resend confirmation email")
        self.assertEqual(CourseRegistration.objects.count(), 1)

    def test_confirmation_payload_contains_confirm_link(self):
        from course_management.datamailer.payloads.registration_confirmations import (
            registration_confirmation_payload,
        )

        with override_settings(
            **RELAY_SETTINGS,
            PUBLIC_BASE_URL="https://courses.example.com",
        ):
            registration = CourseRegistration.objects.create(
                campaign=self.campaign,
                course=self.course,
                email="Student@Example.com",
                name="Student One",
                country="Germany",
                region="Europe",
                role=CourseRegistration.Role.DATA_ENGINEER,
                accepted_newsletter=True,
                email_confirmed=False,
                email_confirmation_token="secret-token-123",
            )
            payload = registration_confirmation_payload(registration)
        self.assertIn(
            "secret-token-123", payload["context"]["confirmation_url"]
        )
        self.assertIn(
            "/register/confirm/", payload["context"]["confirmation_url"]
        )
        self.assertIn(
            "confirmation link", payload["context"]["intro_text"]
        )


class ConfirmLinkTests(RegistrationCampaignBase):
    def create_pending(self, **overrides):
        defaults = {
            "campaign": self.campaign,
            "course": self.course,
            "email": "Student@Example.com",
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "accepted_newsletter": True,
            "email_confirmed": False,
            "email_confirmation_token": "token-abc-123",
            "email_confirmation_sent_at": timezone.now(),
            "email_confirmation_resend_count": 1,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def confirm_url(self, token):
        return reverse("registration_confirm", kwargs={"token": token})

    def test_clicking_link_confirms_registration(self):
        registration = self.create_pending()
        response = self.client.get(self.confirm_url("token-abc-123"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your email is confirmed")
        registration.refresh_from_db()
        self.assertTrue(registration.email_confirmed)
        self.assertIsNotNone(
            registration.email_confirmation_confirmed_at
        )

    def test_confirm_is_idempotent(self):
        registration = self.create_pending()
        first = self.client.get(self.confirm_url("token-abc-123"))
        self.assertEqual(first.status_code, 200)
        second = self.client.get(self.confirm_url("token-abc-123"))
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "already confirmed")
        registration.refresh_from_db()
        self.assertTrue(registration.email_confirmed)

    def test_invalid_token_shows_clear_page(self):
        response = self.client.get(self.confirm_url("no-such-token"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid")
        self.assertEqual(response.context["outcome"], "invalid")

    def test_expired_token_shows_resend_page(self):
        registration = self.create_pending(
            email_confirmation_sent_at=timezone.now()
            - timedelta(days=8),
        )
        response = self.client.get(self.confirm_url("token-abc-123"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")
        self.assertContains(response, "Resend confirmation email")
        registration.refresh_from_db()
        self.assertFalse(registration.email_confirmed)

    def test_confirm_by_token_service_outcomes(self):
        registration = self.create_pending()
        _, outcome = confirm_registration_by_token(
            CourseRegistration, "token-abc-123"
        )
        self.assertEqual(outcome, "confirmed")
        _, outcome = confirm_registration_by_token(
            CourseRegistration, "token-abc-123"
        )
        self.assertEqual(outcome, "already_confirmed")
        _, outcome = confirm_registration_by_token(
            CourseRegistration, "missing"
        )
        self.assertEqual(outcome, "invalid")
        registration.email_confirmed = False
        registration.email_confirmation_sent_at = (
            timezone.now() - timedelta(days=30)
        )
        registration.save()
        _, outcome = confirm_registration_by_token(
            CourseRegistration, "token-abc-123"
        )
        self.assertEqual(outcome, "expired")


class ResendConfirmationTests(RegistrationCampaignBase):
    def create_pending(self, **overrides):
        defaults = {
            "campaign": self.campaign,
            "course": self.course,
            "email": "Student@Example.com",
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "accepted_newsletter": True,
            "email_confirmed": False,
            "email_confirmation_token": "token-resend-1",
            "email_confirmation_sent_at": timezone.now()
            - timedelta(minutes=10),
            "email_confirmation_resend_count": 1,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def resend_url(self):
        return reverse("registration_confirmation_resend")

    @patch(
        "courses.views.registration_confirmation.sync_registration_to_relay"
    )
    @patch(
        "courses.views.registration_confirmation.send_registration_confirmation_email"
    )
    def test_resend_sends_new_confirmation(self, send, sync_datamailer):
        registration = self.create_pending()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.resend_url(),
                {"token": management_token(registration)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmation email sent")
        self.assertContains(response, "Student@Example.com")
        registration.refresh_from_db()
        self.assertNotEqual(
            registration.email_confirmation_token, "token-resend-1"
        )
        self.assertEqual(
            registration.email_confirmation_resend_count, 2
        )
        send.assert_called_once_with(registration)

    def test_resend_rate_limited_by_cooldown(self):
        registration = self.create_pending(
            email_confirmation_sent_at=timezone.now(),
        )
        response = self.client.post(
            self.resend_url(), {"token": management_token(registration)}
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "wait a minute", status_code=429)

    def test_resend_capped_at_max(self):
        registration = self.create_pending(
            email_confirmation_resend_count=EMAIL_CONFIRMATION_MAX_RESENDS,
        )
        response = self.client.post(
            self.resend_url(), {"token": management_token(registration)}
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many", status_code=429)

    def test_resend_confirmed_registration_is_noop(self):
        self.create_pending(
            email_confirmed=True,
            email_confirmation_confirmed_at=timezone.now(),
            email_confirmation_token=None,
        )
        # Confirmed rows have no token; resend with garbage token -> invalid.
        response = self.client.post(
            self.resend_url(), {"token": "nope"}
        )
        self.assertContains(response, "invalid")

    def test_resend_invalid_token(self):
        response = self.client.post(
            self.resend_url(), {"token": "nope"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid")


class FixEmailTests(RegistrationCampaignBase):
    def create_pending(self, **overrides):
        defaults = {
            "campaign": self.campaign,
            "course": self.course,
            "email": "Typo@Example.com",
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "accepted_newsletter": True,
            "email_confirmed": False,
            "email_confirmation_token": "token-fix-1",
            "email_confirmation_sent_at": timezone.now()
            - timedelta(minutes=10),
            "email_confirmation_resend_count": 1,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def fix_url(self):
        return reverse("registration_confirmation_fix_email")

    @patch(
        "courses.views.registration_confirmation.sync_registration_to_relay"
    )
    @patch(
        "courses.views.registration_confirmation.send_registration_confirmation_email"
    )
    def test_fix_email_updates_and_resends(self, send, sync_datamailer):
        registration = self.create_pending()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.fix_url(),
                {
                    "token": management_token(registration),
                    "email": "Fixed@Example.com",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email updated")
        self.assertContains(response, "Fixed@Example.com")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "fixed@example.com"
        )
        self.assertFalse(registration.email_confirmed)
        self.assertNotEqual(
            registration.email_confirmation_token, "token-fix-1"
        )
        send.assert_called_once_with(registration)

    def test_fix_email_rejects_typo_with_suggestion(self):
        registration = self.create_pending()
        response = self.client.post(
            self.fix_url(),
            {
                "token": management_token(registration),
                "email": "user@gmial.com",
            },
        )
        self.assertContains(response, "Did you mean user@gmail.com?")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "typo@example.com"
        )

    def test_fix_email_rejects_domain_without_mx(self):
        import dns.resolver

        registration = self.create_pending()
        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.resolver.NXDOMAIN(),
        ):
            response = self.client.post(
                self.fix_url(),
                {
                    "token": management_token(registration),
                    "email": "user@no-mx-here.com",
                },
            )
        self.assertContains(response, "does not accept mail")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "typo@example.com"
        )

    def test_fix_email_rejects_duplicate(self):
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="taken@example.com",
            name="Taken",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )
        registration = self.create_pending()
        response = self.client.post(
            self.fix_url(),
            {
                "token": management_token(registration),
                "email": "taken@example.com",
            },
        )
        self.assertContains(response, "already registered")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "typo@example.com"
        )


class BackfillMigrationTests(RegistrationCampaignBase):
    def test_backfill_marks_existing_confirmed(self):
        import importlib

        migration = importlib.import_module(
            "courses.migrations.0052_backfill_registration_email_confirmed"
        )
        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="old@example.com",
            name="Old Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
            email_confirmed=False,
        )
        migration.mark_existing_registrations_confirmed(apps, None)
        registration.refresh_from_db()
        self.assertTrue(registration.email_confirmed)
        self.assertIsNotNone(
            registration.email_confirmation_confirmed_at
        )
        self.assertIsNone(registration.email_confirmation_token)


class FullConfirmationE2ETests(RegistrationCampaignBase):
    """Register -> pending page -> confirm link -> confirmed."""

    @override_settings(**RELAY_SETTINGS)
    @patch("courses.views.registration.sync_registration_to_relay")
    @patch(
        "courses.views.registration.send_registration_confirmation_email"
    )
    @patch(
        "courses.email_validation._mx_records_for_domain",
        return_value=_fake_mx(),
    )
    def test_full_flow(
        self, mx_records, send_confirmation, sync_datamailer
    ):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.campaign_url(),
                self.registration_payload(email="Flow@Example.com"),
            )
        self.assertContains(
            response, "MUST click the confirmation link"
        )
        registration = CourseRegistration.objects.get()
        token = registration.email_confirmation_token
        self.assertFalse(registration.email_confirmed)

        confirm_response = self.client.get(
            reverse("registration_confirm", kwargs={"token": token})
        )
        self.assertContains(confirm_response, "Your email is confirmed")
        registration.refresh_from_db()
        self.assertTrue(registration.email_confirmed)

    @override_settings(**RELAY_SETTINGS)
    @patch(
        "courses.views.registration_confirmation.sync_registration_to_relay"
    )
    @patch(
        "courses.views.registration_confirmation.send_registration_confirmation_email"
    )
    def test_dashboard_resend_flow(
        self, send_confirmation, sync_datamailer
    ):
        user = self.create_signed_user()
        self.client.force_login(user)
        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=user,
            email=user.email,
            name="Signed Student",
            country="Canada",
            region="North America",
            role=CourseRegistration.Role.DATA_SCIENTIST,
            accepted_newsletter=True,
            email_confirmed=False,
            email_confirmation_token="token-dash-1",
            email_confirmation_sent_at=timezone.now()
            - timedelta(minutes=10),
            email_confirmation_resend_count=1,
        )
        settings_response = self.client.get(reverse("account_settings"))
        self.assertContains(settings_response, "Unconfirmed")
        self.assertContains(settings_response, "Resend confirmation")
        with self.captureOnCommitCallbacks(execute=True):
            resend_response = self.client.post(
                reverse("registration_confirmation_resend"),
                {"token": management_token(registration)},
            )
        self.assertContains(resend_response, "Confirmation email sent")
        registration.refresh_from_db()
        self.assertFalse(registration.email_confirmed)


class ResolverTimeoutTests(TestCase):
    def test_dns_timeout_is_logged_and_lookup_is_bounded(self):
        import dns.exception
        from unittest.mock import patch
        from courses.email_validation import (
            domain_has_mx,
            _mx_records_for_domain,
            DNS_LOOKUP_TIMEOUT_SECONDS,
        )

        with patch(
            "courses.email_validation._mx_records_for_domain",
            side_effect=dns.exception.Timeout(),
        ):
            with self.assertLogs(
                "courses.email_validation", level="WARNING"
            ):
                self.assertIsNone(domain_has_mx("flaky-dns.com"))
        with patch(
            "courses.email_validation.dns.resolver.Resolver"
        ) as factory:
            _mx_records_for_domain("gmail.com")
            self.assertEqual(
                factory.return_value.lifetime,
                DNS_LOOKUP_TIMEOUT_SECONDS,
            )
            self.assertEqual(
                factory.return_value.timeout, DNS_LOOKUP_TIMEOUT_SECONDS
            )
