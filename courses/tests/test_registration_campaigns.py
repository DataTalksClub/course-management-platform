from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    Homework,
    HomeworkState,
    RegistrationCampaign,
)


class RegistrationCampaignPublicTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )
        self.campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            edition_label="2026 cohort",
            current_course=self.course,
            marketing_markdown="## Learn LLMs\n\nBuild useful apps.",
        )

    def registration_payload(self, email="Student@Example.com"):
        return {
            "email": email,
            "name": "Student One",
            "country": "Germany",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "comment": "Looking forward to it",
            "accepted_newsletter": "on",
        }

    def test_registration_page_renders_campaign_content(self):
        response = self.client.get(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")
        self.assertContains(response, "Build useful apps")
        self.assertContains(response, "Register")

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_anonymous_registration_creates_independent_registration(
        self,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "registration_campaign",
                    kwargs={"campaign_slug": self.campaign.slug},
                ),
                self.registration_payload(),
            )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "student@example.com"
        )
        self.assertEqual(registration.course, self.course)
        self.assertEqual(registration.region, "Europe")
        self.assertIsNone(registration.user)

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

        response = self.client.post(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
            self.registration_payload(email="student@example.com"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You have already registered for this course.",
        )
        self.assertEqual(CourseRegistration.objects.count(), 1)

    @override_settings(
        DATAMAILER_URL="",
        DATAMAILER_API_KEY="",
        DATAMAILER_CLIENT="",
        DATAMAILER_AUDIENCE="",
    )
    def test_registration_requires_only_email_and_newsletter_consent(self):
        response = self.client.post(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
            {
                "email": "email-only@example.com",
                "accepted_newsletter": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "email-only@example.com"
        )
        self.assertEqual(registration.name, "")
        self.assertEqual(registration.country, "")
        self.assertEqual(registration.region, "")
        self.assertEqual(registration.role, "")
        self.assertTrue(registration.accepted_newsletter)

    def test_registration_requires_newsletter_consent(self):
        response = self.client.post(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
            {"email": "email-only@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This field is required.",
        )
        self.assertEqual(CourseRegistration.objects.count(), 0)

    def test_logged_in_user_registration_uses_account_email(self):
        user = CustomUser.objects.create_user(
            username="signed",
            email="signed@example.com",
            password="test",
            certificate_name="Signed Student",
            country="Canada",
            region="North America",
            registration_role=CourseRegistration.Role.DATA_SCIENTIST,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )

        self.assertContains(response, 'value="Signed Student"')
        self.assertContains(response, 'value="Canada"')
        self.assertContains(
            response,
            '<option value="data_scientist" selected>Data Scientist</option>',
            html=True,
        )

        response = self.client.post(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
            {
                **self.registration_payload(email="other@example.com"),
                "name": "Updated Certificate Name",
                "country": "Germany",
                "role": CourseRegistration.Role.DATA_ENGINEER,
            },
        )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "signed@example.com"
        )
        self.assertEqual(registration.user, user)
        user.refresh_from_db()
        self.assertEqual(
            user.certificate_name, "Updated Certificate Name"
        )
        self.assertEqual(user.country, "Germany")
        self.assertEqual(user.region, "Europe")
        self.assertEqual(
            user.registration_role,
            CourseRegistration.Role.DATA_ENGINEER,
        )

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
        user = CustomUser.objects.create_user(
            username="signed-blank",
            email="signed-blank@example.com",
            password="test",
            certificate_name="Existing Name",
            country="Canada",
            region="North America",
            registration_role=CourseRegistration.Role.DATA_SCIENTIST,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
            {
                "email": "ignored@example.com",
                "accepted_newsletter": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.email_normalized, "signed-blank@example.com"
        )
        self.assertEqual(registration.name, "")
        self.assertEqual(registration.country, "")
        self.assertEqual(registration.region, "")
        self.assertEqual(registration.role, "")
        user.refresh_from_db()
        self.assertEqual(user.certificate_name, "Existing Name")
        self.assertEqual(user.country, "Canada")
        self.assertEqual(user.region, "North America")
        self.assertEqual(
            user.registration_role,
            CourseRegistration.Role.DATA_SCIENTIST,
        )

    def test_empty_course_redirects_non_staff_to_campaign(self):
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertRedirects(
            response,
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            ),
        )

    def test_course_with_homework_shows_workspace_and_registration_link(
        self,
    ):
        Homework.objects.create(
            course=self.course,
            slug="intro",
            title="Intro",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.OPEN.value,
        )

        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Register")
        self.assertContains(response, "Intro")

    def test_course_page_hides_registration_button_when_registered(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="registered",
            email="registered@example.com",
            password="test",
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=user,
            email=user.email,
            name="Registered Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )
        Homework.objects.create(
            course=self.course,
            slug="intro",
            title="Intro",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.OPEN.value,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Register")

    def test_course_page_hides_registration_button_when_enrolled(self):
        user = CustomUser.objects.create_user(
            username="enrolled",
            email="enrolled@example.com",
            password="test",
        )
        Enrollment.objects.create(student=user, course=self.course)
        Homework.objects.create(
            course=self.course,
            slug="intro",
            title="Intro",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.OPEN.value,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Register")

    def test_registration_page_shows_already_registered_for_logged_in_user(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="registered",
            email="registered@example.com",
            password="test",
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=user,
            email=user.email,
            name="Registered Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "registration_campaign",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )

        self.assertContains(response, "You are already registered")
        self.assertNotContains(response, 'name="email"')

    @override_settings(
        DATAMAILER_URL="https://datamailer.example.com",
        DATAMAILER_API_KEY="secret-token",
        DATAMAILER_CLIENT="dtc-courses",
        DATAMAILER_AUDIENCE="dtc-courses",
    )
    @patch(
        "courses.views.registration.send_registration_confirmation_email"
    )
    @patch("courses.views.registration.sync_registration_to_datamailer")
    def test_registration_syncs_to_datamailer_and_sends_confirmation(
        self,
        sync_datamailer,
        send_confirmation,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "registration_campaign",
                    kwargs={"campaign_slug": self.campaign.slug},
                ),
                self.registration_payload(),
            )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        sync_datamailer.assert_called_once_with(registration)
        send_confirmation.assert_called_once_with(registration)
