from datetime import date

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.urls import reverse
from django.utils.formats import date_format

from accounts.models import CustomUser
from course_management.relay.application_notifications import (
    notification_context,
)
from courses.admin.course import CourseAdmin
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class AcceptedStudentInfoTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.start_date = date(2026, 11, 16)
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/"
            "production-ai-agents-for-media-generation"
        )
        self.course.live_session_schedule_details = (
            "Pre-course Q&A: Tue 10 Nov 2026, "
            "17:00–18:00 Europe/Berlin"
        )
        self.course.live_session_schedule_url = "https://luma.com/i4x6x2zy"
        self.course.support_channel_name = "#course-ai-mediagen on Slack"
        self.course.support_channel_url = (
            "https://app.slack.com/client/T01ATQK62F8/C0CEG1BUDKL"
        )
        self.course.support_email = ""
        self.course.save()

    def test_accepted_course_page_shows_information_before_and_after_start(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="accepted-info-student",
            email="accepted-info-student@example.com",
            password="test",
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=user,
            email=user.email,
            name="Accepted Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            status=CourseRegistration.Status.APPROVED,
        )
        Enrollment.objects.create(student=user, course=self.course)
        self.client.force_login(user)
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        for start_date in (date(2026, 11, 16), date(2026, 10, 1)):
            self.course.start_date = start_date
            self.course.save(update_fields=["start_date"])
            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Course starts")
            self.assertContains(response, date_format(start_date, "D j M Y"))
            self.assertContains(response, "Q&amp;A: Tue 10 Nov 2026")
            self.assertContains(response, "https://luma.com/i4x6x2zy")
            self.assertContains(response, "All course content is on GitHub")
            self.assertContains(response, self.course.github_repo_url)
            page_text = " ".join(response.content.decode().split())
            self.assertIn(
                "This page is only for logistics: homework, submissions, "
                "projects, and leaderboard.",
                page_text,
            )
            self.assertContains(response, self.course.support_channel_name)
            self.assertContains(response, self.course.support_channel_url)

    def test_registration_page_shows_course_materials_and_help(self):
        response = self.client.get(self.campaign_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All course content is on GitHub")
        self.assertContains(response, self.course.github_repo_url)
        self.assertContains(response, "17:00–18:00 Europe/Berlin")
        self.assertContains(response, self.course.support_channel_name)
        page_text = " ".join(response.content.decode().split())
        self.assertIn(
            "This page is only for logistics: homework, submissions, "
            "projects, and leaderboard.",
            page_text,
        )

    def test_approval_email_contains_course_information_and_reviewer_note(
        self,
    ):
        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="accepted-info-student@example.com",
            name="Accepted Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            status=CourseRegistration.Status.APPROVED,
        )

        context = notification_context(
            registration,
            custom_message="Looking forward to seeing you.",
        )

        self.assertIn(
            "Course starts: Mon 16 Nov 2026",
            context["custom_message"],
        )
        self.assertIn(
            "Tue 10 Nov 2026, 17:00–18:00 Europe/Berlin",
            context["custom_message"],
        )
        self.assertIn(
            "https://luma.com/i4x6x2zy",
            context["custom_message"],
        )
        self.assertIn(
            "All course content is on GitHub",
            context["custom_message"],
        )
        self.assertIn(self.course.github_repo_url, context["custom_message"])
        self.assertIn(
            "homework, submissions, projects, and leaderboard",
            context["custom_message"],
        )
        self.assertIn(
            self.course.support_channel_name,
            context["custom_message"],
        )
        self.assertIn("Looking forward to seeing you.", context["custom_message"])
        self.assertIn(
            f'href="{self.course.github_repo_url}"',
            context["custom_message_html"],
        )
        self.assertIn(
            f'href="{self.course.support_channel_url}"',
            context["custom_message_html"],
        )

    def test_course_information_fields_are_editable(self):
        request = RequestFactory().get("/admin/")
        admin_fields = CourseAdmin(Course, AdminSite()).get_fields(request)
        for field_name in (
            "live_session_schedule_details",
            "live_session_schedule_url",
            "support_channel_name",
            "support_channel_url",
            "support_email",
        ):
            with self.subTest(field=field_name):
                self.assertTrue(
                    Course._meta.get_field(field_name).editable
                )
                self.assertIn(field_name, admin_fields)

    def test_production_course_configuration_is_seeded(self):
        course = Course.objects.get(
            slug="production-ai-agents-generative-media"
        )
        campaign = RegistrationCampaign.objects.get(
            slug="production-ai-agents-generative-media"
        )

        self.assertEqual(course.start_date, date(2026, 11, 16))
        self.assertEqual(
            course.github_repo_url,
            "https://github.com/DataTalksClub/"
            "production-ai-agents-for-media-generation",
        )
        self.assertEqual(
            course.live_session_schedule_url,
            "https://luma.com/i4x6x2zy",
        )
        self.assertIn(
            "17:00–18:00 Europe/Berlin",
            campaign.marketing_markdown,
        )
        self.assertIn(
            "Course starts: Mon 16 Nov 2026",
            campaign.marketing_markdown,
        )
        self.assertNotIn(
            "Course starts: Mon 17 Nov 2026",
            campaign.marketing_markdown,
        )
