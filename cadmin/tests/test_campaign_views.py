from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from courses.models import Course, CourseRegistration, RegistrationCampaign, User


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)

admin_credentials = dict(
    username="admin@test.com",
    password="admin123",
)


class CampaignCadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_llm_registration_campaign(self, **overrides):
        defaults = {
            "slug": "llm-zoomcamp",
            "title": "LLM Zoomcamp",
            "current_course": self.course,
            "marketing_markdown": "Register now",
        }
        defaults.update(overrides)
        return RegistrationCampaign.objects.create(**defaults)

    def campaign_edit_payload(self):
        return {
            "title": "LLM Zoomcamp 2026",
            "slug": "llm-zoomcamp",
            "edition_label": "",
            "current_course": self.course.id,
            "is_active": "on",
            "hero_image_url": "",
            "video_url": "",
            "meta_description": "",
            "marketing_markdown": "New copy",
        }

    def campaign_create_payload(self):
        return {
            "title": "LLM Zoomcamp",
            "slug": "llm-zoomcamp",
            "edition_label": "2026 cohort",
            "current_course": self.course.id,
            "is_active": "on",
            "hero_image_url": "https://example.com/hero.jpg",
            "video_url": "https://youtu.be/example",
            "meta_description": "Learn LLMs",
            "marketing_markdown": "## Register now",
        }

    def assert_campaign_create_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create registration landing page")
        self.assertContains(response, self.course.title)

    def assert_campaign_edit_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit registration landing page")
        self.assertContains(response, "/register/llm-zoomcamp/")

    def assert_created_campaign_saved(self, campaign):
        self.assertEqual(campaign.current_course, self.course)
        self.assertEqual(campaign.marketing_markdown, "## Register now")

    def assert_campaign_updated(self, campaign):
        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "LLM Zoomcamp 2026")
        self.assertEqual(campaign.marketing_markdown, "New copy")

    def assert_campaign_draft_upserted(self, upsert_campaign):
        upsert_campaign.assert_called_once()
        self.assertEqual(
            upsert_campaign.call_args.args[0],
            "cmp-registration-llm-zoomcamp",
        )
        payload = upsert_campaign.call_args.args[1]
        self.assertEqual(payload["subject"], "LLM Zoomcamp")
        self.assertEqual(payload["preview_text"], "Learn LLMs")
        self.assertIn("<h2>Register now</h2>", payload["html_body"])
        self.assertEqual(payload["text_body"], "## Register now")
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(payload["recipient_list_key"], self.course.slug)
        self.assertEqual(
            payload["metadata"]["registration_url"],
            "https://courses.example.com/register/llm-zoomcamp/",
        )
        self.assertEqual(
            payload["metadata"]["course_slug"], self.course.slug
        )

    def test_campaign_registrations_staff_allowed(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=self.course,
            email="student@example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        self.client.login(**admin_credentials)
        url = reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "Europe")

    def test_campaign_create_staff_allowed(self):
        self.client.login(**admin_credentials)
        url = reverse("cadmin_campaign_create")
        response = self.client.get(f"{url}?course={self.course.slug}")

        self.assert_campaign_create_page(response)

        payload = self.campaign_create_payload()
        response = self.client.post(url, payload)

        campaign = RegistrationCampaign.objects.get(slug="llm-zoomcamp")
        redirect_url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        self.assertRedirects(response, redirect_url)
        self.assert_created_campaign_saved(campaign)

    def test_campaign_create_non_staff_denied(self):
        self.client.login(**credentials)
        url = reverse("cadmin_campaign_create")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(RegistrationCampaign.objects.exists())

    def test_campaign_edit_staff_allowed(self):
        campaign = self.create_llm_registration_campaign(
            marketing_markdown="Old copy",
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assert_campaign_edit_page(response)

        payload = self.campaign_edit_payload()
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        self.assert_campaign_updated(campaign)

    def test_campaign_edit_shows_datamailer_campaign_controls(self):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datamailer campaign")
        self.assertContains(response, "cmp-registration-llm-zoomcamp")
        self.assertContains(response, self.course.slug)
        self.assertContains(response, "Sync draft")
        self.assertContains(response, "Test send")

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_syncs_datamailer_campaign_draft(
        self, upsert_campaign
    ):
        campaign = self.create_llm_registration_campaign(
            meta_description="Learn LLMs",
            marketing_markdown="## Register now",
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "sync"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        self.assert_campaign_draft_upserted(upsert_campaign)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.preview_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_previews_datamailer_campaign(
        self, upsert_campaign, preview_campaign
    ):
        preview_campaign.return_value = {
            "preview": {
                "subject": "Preview subject",
                "text": "Preview text",
            }
        }
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "preview"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        upsert_campaign.assert_called_once()
        preview_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )
        self.assertContains(response, "Preview subject")
        self.assertContains(response, "Preview text")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.test_send_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_sends_datamailer_campaign_test(
        self, upsert_campaign, test_send_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {
            "datamailer_action": "test_send",
            "test_recipients": "ops@example.com, reviewer@example.com",
        }

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        expected_recipients = ["ops@example.com", "reviewer@example.com"]
        test_send_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp",
            expected_recipients,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.queue_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_queues_datamailer_campaign(
        self, upsert_campaign, queue_campaign
    ):
        queue_campaign.return_value = {"recipient_count": 42}
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "queue"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        queue_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.cancel_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_cancels_datamailer_campaign_without_upsert(
        self, upsert_campaign, cancel_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "cancel"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_not_called()
        cancel_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )
