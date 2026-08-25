from django.test import override_settings
from django.urls import reverse

from courses.models import (
    CourseRegistration,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class RegistrationCampaignPublicTests(RegistrationCampaignBase):
    def test_registration_page_renders_campaign_content(self):
        url = self.campaign_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")
        self.assertContains(response, "Build useful apps")
        self.assertContains(response, "Register")
        self.assertContains(response, "Company name")

    def test_registration_page_shows_signup_count_for_cohort(self):
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="a@example.com",
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="b@example.com",
        )

        response = self.client.get(self.campaign_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 already registered")

    def test_signup_count_is_specific_to_the_cohort(self):
        from courses.models import Course, RegistrationCampaign

        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="a@example.com",
        )

        other_course = Course.objects.create(
            slug="llm-zoomcamp-2027",
            title="LLM Zoomcamp 2027",
            description="Next edition",
        )
        other_campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp-next",
            title="LLM Zoomcamp Next",
            edition_label="2027 cohort",
            current_course=other_course,
        )
        CourseRegistration.objects.create(
            campaign=other_campaign,
            course=other_course,
            email="b@example.com",
        )
        CourseRegistration.objects.create(
            campaign=other_campaign,
            course=other_course,
            email="c@example.com",
        )

        response = self.client.get(self.campaign_url())

        self.assertContains(response, "1 already registered")
        self.assertNotContains(response, "3 already registered")

    def test_registration_page_hides_count_when_no_signups(self):
        response = self.client.get(self.campaign_url())

        self.assertNotContains(response, "already registered")

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_anonymous_registration_creates_independent_registration(
        self,
    ):
        url = self.campaign_url()
        payload = self.registration_payload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                payload,
            )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "student@example.com"
        )
        self.assertEqual(registration.course, self.course)
        self.assertEqual(registration.region, "Europe")
        self.assertIsNone(registration.user)

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_registration_stores_optional_company_name(self):
        url = self.campaign_url()
        payload = self.registration_payload()
        payload["company_name"] = "Acme Data"

        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.company_name, "Acme Data")

    def test_duplicate_registration_shows_message(self):
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="student@example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        url = self.campaign_url()
        payload = self.registration_payload(email="student@example.com")
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You have already registered for this course.",
        )
        registration_count = CourseRegistration.objects.count()
        self.assertEqual(registration_count, 1)

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_registration_requires_only_email_and_newsletter_consent(self):
        url = self.campaign_url()
        payload = {
            "email": "email-only@example.com",
            "accepted_newsletter": "on",
        }
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "email-only@example.com"
        )
        self.assertEqual(registration.name, "")
        self.assertEqual(registration.company_name, "")
        self.assertEqual(registration.country, "")
        self.assertEqual(registration.region, "")
        self.assertEqual(registration.role, "")
        self.assertTrue(registration.accepted_newsletter)

    def test_registration_requires_newsletter_consent(self):
        url = self.campaign_url()
        payload = {"email": "email-only@example.com"}
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This field is required.",
        )
        registration_count = CourseRegistration.objects.count()
        self.assertEqual(registration_count, 0)

    def test_logged_in_user_registration_uses_account_email(self):
        user = self.create_signed_user()
        self.client.force_login(user)

        url = self.campaign_url()
        response = self.client.get(url)

        self.assert_signed_profile_form(response)

        payload = self.updated_account_payload()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assert_logged_in_registration(registration, user)
        self.assert_signed_profile_updated(user)

    def test_logged_in_registration_page_shows_logout_link(self):
        user = self.create_signed_user()
        self.client.force_login(user)

        url = self.campaign_url()
        response = self.client.get(url)

        logout_url = reverse("account_logout")
        self.assertContains(response, "Log out")
        self.assertContains(response, f"{logout_url}?next=")
        self.assertContains(response, "to use a different email address")

    def test_anonymous_registration_page_does_not_show_logout_link(self):
        url = self.campaign_url()
        response = self.client.get(url)

        self.assertNotContains(response, "to use a different email address")

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_logged_in_registration_blank_optional_fields_keeps_profile(self):
        user = self.create_signed_blank_user()
        self.client.force_login(user)

        url = self.campaign_url()
        payload = self.blank_optional_logged_in_payload()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assert_blank_logged_in_registration(registration, user)
        self.assert_signed_blank_profile_unchanged(user)

    def test_registration_page_shows_already_registered_for_logged_in_user(
        self,
    ):
        user = self.create_registered_course_user()
        self.client.force_login(user)

        url = reverse(
            "registration_campaign",
            kwargs={"campaign_slug": self.campaign.slug},
        )
        response = self.client.get(url)

        self.assertContains(response, "You are already registered")
        self.assertNotContains(response, 'name="email"')


class RegistrationCampaignMalformedEmailTests(RegistrationCampaignBase):
    """Guards against malformed emails that leaked into old
    Airtable/Google-Form CSV imports (missing "@", missing "." in the
    domain, stray "@" characters, truncated domains, punctuation in the
    local part, trailing garbage, or non-email identifiers). The live
    public registration form must reject all of these."""

    def assert_email_rejected(self, email):
        url = self.campaign_url()
        payload = self.registration_payload(email=email)
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertEqual(CourseRegistration.objects.count(), 0)

    def test_registration_rejects_email_missing_at_sign(self):
        self.assert_email_rejected("testuser42examplecom")

    def test_registration_rejects_email_missing_dot_in_domain(self):
        self.assert_email_rejected("testuser@examplecom")

    def test_registration_rejects_email_with_stray_extra_at_sign(self):
        self.assert_email_rejected("testuser@@example.com")

    def test_registration_rejects_email_with_at_sign_in_middle(self):
        self.assert_email_rejected("testuser@middle@example.com")

    def test_registration_rejects_email_with_truncated_domain(self):
        self.assert_email_rejected("testuser@e")

    def test_registration_rejects_email_with_incomplete_domain_no_dot(self):
        self.assert_email_rejected("testuser@protonmailclone")

    def test_registration_rejects_email_with_comma_in_local_part(self):
        self.assert_email_rejected("test,user@example.com")

    def test_registration_rejects_email_with_semicolon_in_local_part(self):
        self.assert_email_rejected("test;user@example.com")

    def test_registration_rejects_email_with_trailing_garbage_suffix(self):
        self.assert_email_rejected("testuser@example.com_extra")

    def test_registration_rejects_email_with_trailing_garbage_text(self):
        self.assert_email_rejected("testuser@example.com au")

    def test_registration_rejects_payment_id_typed_as_email(self):
        self.assert_email_rejected("testuser@okbankid")

    def test_registration_rejects_bare_username_as_email(self):
        self.assert_email_rejected("plainusername42")

    def test_registration_rejects_plain_text_as_email(self):
        self.assert_email_rejected("not sure what to type here")
