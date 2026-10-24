from courses.tests.registration_campaign_base import (
    RegistrationCampaignBase,
)


class PendingConfirmationRegressionTests(RegistrationCampaignBase):
    def test_submission_requires_confirmation_and_shows_typed_address(
        self,
    ):
        response = self.client.post(
            self.campaign_url(),
            self.registration_payload(email="Student@Example.com"),
        )
        self.assertContains(
            response, "You MUST click the confirmation link"
        )
        self.assertContains(response, "Student@Example.com")
        self.assertContains(response, "Resend confirmation")

    def test_pending_page_does_not_expose_email_confirmation_secret(
        self,
    ):
        from courses.models import CourseRegistration

        response = self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        registration = CourseRegistration.objects.get()
        self.assertNotIn(
            registration.email_confirmation_token,
            response.content.decode(),
        )

    def test_resends_have_distinct_delivery_keys(self):
        from django.test import override_settings
        from course_management.datamailer.payloads.registration_confirmations import (
            registration_confirmation_payload,
        )
        from courses.models import CourseRegistration

        with override_settings(
            RELAY_URL="https://relay.example.com",
            RELAY_API_KEY="test",
            RELAY_CLIENT="dtc-courses",
            RELAY_AUDIENCE="dtc-courses",
        ):
            registration = CourseRegistration(
                campaign=self.campaign,
                course=self.course,
                email="test@example.com",
                pk=42,
                email_confirmation_token="first",
            )
            first = registration_confirmation_payload(registration)
            registration.email_confirmation_token = "second"
            second = registration_confirmation_payload(registration)
        self.assertNotEqual(
            first["idempotency_key"], second["idempotency_key"]
        )

    def test_duplicate_in_another_browser_cannot_manage_registration(
        self,
    ):
        from django.test import Client
        from courses.models import CourseRegistration

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        response = Client().post(
            self.campaign_url(), self.registration_payload()
        )
        self.assertContains(response, "already registered")
        self.assertNotContains(response, "data-pending-confirmation")
        registration = CourseRegistration.objects.get()
        self.assertNotIn(
            registration.email_confirmation_token,
            response.content.decode(),
        )

    def test_confirmation_secret_cannot_be_used_to_correct_address(
        self,
    ):
        from courses.models import CourseRegistration

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        registration = CourseRegistration.objects.get()
        self.client.post(
            "/register/fix-email/",
            {
                "token": registration.email_confirmation_token,
                "email": "attacker@example.com",
            },
        )
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "student@example.com"
        )

    def test_management_token_cannot_confirm_email(self):
        from courses.models import CourseRegistration
        from courses.registration_confirmation import management_token

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        registration = CourseRegistration.objects.get()
        response = self.client.get(
            "/register/confirm/" + management_token(registration) + "/"
        )
        self.assertContains(response, "invalid")
        self.assertContains(response, "Resend confirmation email")
        registration.refresh_from_db()
        self.assertFalse(registration.email_confirmed)

    def test_correction_and_resend_share_limits_and_revoke_old_management(
        self,
    ):
        from datetime import timedelta
        from django.utils import timezone
        from courses.models import CourseRegistration
        from courses.registration_confirmation import management_token

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        registration = CourseRegistration.objects.get()
        old_management = management_token(registration)
        response = self.client.post(
            "/register/fix-email/",
            {
                "token": old_management,
                "email": "fixed@example.com",
            },
        )
        self.assertEqual(response.status_code, 429)
        CourseRegistration.objects.filter(pk=registration.pk).update(
            email_confirmation_sent_at=timezone.now()
            - timedelta(minutes=2)
        )
        with self.captureOnCommitCallbacks(execute=False):
            response = self.client.post(
                "/register/fix-email/",
                {
                    "token": old_management,
                    "email": "Fixed@Example.com",
                },
            )
        self.assertContains(response, "Fixed@Example.com")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_confirmation_resend_count, 2
        )
        self.assertEqual(
            registration.email_normalized, "fixed@example.com"
        )
        response = self.client.post(
            "/register/fix-email/",
            {
                "token": old_management,
                "email": "third@example.com",
            },
        )
        self.assertContains(response, "invalid")
        registration.refresh_from_db()
        self.assertEqual(
            registration.email_normalized, "fixed@example.com"
        )

    def test_invalid_link_recovery_sends_without_disclosing_registration(
        self,
    ):
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from courses.models import CourseRegistration

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        CourseRegistration.objects.update(
            email_confirmation_sent_at=timezone.now()
            - timedelta(minutes=2)
        )
        with patch(
            "courses.views.registration_confirmation.send_registration_confirmation_email"
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/register/resend-confirmation/",
                    {
                        "email": "student@example.com",
                        "campaign_slug": self.campaign.slug,
                    },
                )
            send.assert_called_once()
        self.assertContains(
            response, "If an unconfirmed registration matches"
        )
        registration = CourseRegistration.objects.get()
        self.assertNotIn(
            registration.email_confirmation_token,
            response.content.decode(),
        )
        missing = self.client.post(
            "/register/resend-confirmation/",
            {
                "email": "missing@example.com",
                "campaign_slug": self.campaign.slug,
            },
        )
        self.assertContains(
            missing, "If an unconfirmed registration matches"
        )

    def test_migration_replay_preserves_token_bearing_pending_rows(
        self,
    ):
        import importlib
        from django.apps import apps
        from courses.models import CourseRegistration

        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        importlib.import_module(
            "courses.migrations.0052_backfill_registration_email_confirmed"
        ).mark_existing_registrations_confirmed(apps, None)
        self.assertFalse(
            CourseRegistration.objects.get().email_confirmed
        )

    def test_published_template_source_renders_clickable_confirmation(
        self,
    ):
        from django.template import Context, Template
        from course_management.datamailer_templates.definitions.submissions import (
            SUBMISSION_TEMPLATES,
        )

        definition = SUBMISSION_TEMPLATES["registration-confirmation"]
        context = dict(definition["example_context"])
        context["confirmation_url"] = (
            "https://courses.example.com/register/confirm/secret/"
        )
        html = Template(definition["html_body"]).render(
            Context(context)
        )
        text = Template(definition["text_body"]).render(
            Context(context)
        )
        self.assertIn(
            'href="' + context["confirmation_url"] + '"', html
        )
        self.assertIn(context["confirmation_url"], text)
        self.assertIn("MUST click", text)

    def test_profile_keeps_account_link_after_correcting_registration_email(
        self,
    ):
        from datetime import timedelta
        from django.utils import timezone
        from courses.models import CourseRegistration

        user = self.create_signed_user()
        self.client.force_login(user)
        self.client.post(
            self.campaign_url(), self.registration_payload()
        )
        registration = CourseRegistration.objects.get()
        CourseRegistration.objects.filter(pk=registration.pk).update(
            email_confirmation_sent_at=timezone.now()
            - timedelta(minutes=2)
        )
        response = self.client.post(
            "/register/fix-email/",
            {
                "token": registration.confirmation_management_token,
                "email": "Fixed@Example.com",
            },
        )
        self.assertContains(response, "Email updated")
        response = self.client.get(self.campaign_url())
        self.assertContains(response, "Fixed@Example.com")
        self.assertContains(response, "Resend confirmation")
        user.refresh_from_db()
        self.assertEqual(user.email, "signed@example.com")
