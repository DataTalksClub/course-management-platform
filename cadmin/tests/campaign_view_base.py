from django.test import Client, TestCase

from courses.models import Course, RegistrationCampaign, User


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


class CampaignCadminViewBase(TestCase):
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
