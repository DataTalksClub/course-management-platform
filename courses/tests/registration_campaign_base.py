from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    Course,
    CourseRegistration,
    Homework,
    HomeworkState,
    RegistrationCampaign,
)


class RegistrationCampaignBase(TestCase):
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

    def campaign_url(self):
        return reverse(
            "registration_campaign",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    def create_signed_user(self):
        return CustomUser.objects.create_user(
            username="signed",
            email="signed@example.com",
            password="test",
            certificate_name="Signed Student",
            country="Canada",
            region="North America",
            registration_role=CourseRegistration.Role.DATA_SCIENTIST,
        )

    def create_signed_blank_user(self):
        return CustomUser.objects.create_user(
            username="signed-blank",
            email="signed-blank@example.com",
            password="test",
            certificate_name="Existing Name",
            country="Canada",
            region="North America",
            registration_role=CourseRegistration.Role.DATA_SCIENTIST,
        )

    def updated_account_payload(self):
        payload = self.registration_payload(email="other@example.com")
        payload["name"] = "Updated Certificate Name"
        payload["country"] = "Germany"
        payload["role"] = CourseRegistration.Role.DATA_ENGINEER
        return payload

    def blank_optional_logged_in_payload(self):
        return {
            "email": "ignored@example.com",
            "accepted_newsletter": "on",
        }

    def assert_signed_profile_form(self, response):
        self.assertContains(response, 'value="Signed Student"')
        self.assertContains(response, 'value="Canada"')
        self.assertContains(
            response,
            '<option value="data_scientist" selected>Data Scientist</option>',
            html=True,
        )

    def assert_logged_in_registration(self, registration, user):
        self.assertEqual(registration.email_normalized, "signed@example.com")
        self.assertEqual(registration.user, user)

    def assert_signed_profile_updated(self, user):
        user.refresh_from_db()
        self.assertEqual(user.certificate_name, "Updated Certificate Name")
        self.assertEqual(user.country, "Germany")
        self.assertEqual(user.region, "Europe")
        self.assertEqual(
            user.registration_role,
            CourseRegistration.Role.DATA_ENGINEER,
        )

    def assert_blank_logged_in_registration(self, registration, user):
        self.assertEqual(
            registration.email_normalized, "signed-blank@example.com"
        )
        self.assertEqual(registration.name, "")
        self.assertEqual(registration.country, "")
        self.assertEqual(registration.region, "")
        self.assertEqual(registration.role, "")
        self.assertEqual(registration.user, user)

    def assert_signed_blank_profile_unchanged(self, user):
        user.refresh_from_db()
        self.assertEqual(user.certificate_name, "Existing Name")
        self.assertEqual(user.country, "Canada")
        self.assertEqual(user.region, "North America")
        self.assertEqual(
            user.registration_role,
            CourseRegistration.Role.DATA_SCIENTIST,
        )

    def create_registered_course_user(self):
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
        return user

    def create_intro_homework(self):
        due_date = timezone.now()
        return Homework.objects.create(
            course=self.course,
            slug="intro",
            title="Intro",
            description="",
            due_date=due_date,
            state=HomeworkState.OPEN.value,
        )
