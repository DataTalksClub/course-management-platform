from django.urls import reverse

from accounts.models import CustomUser
from courses.models import Enrollment
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class RegistrationCampaignCoursePageTests(RegistrationCampaignBase):
    def test_empty_course_redirects_non_staff_to_campaign(self):
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        redirect_url = reverse(
            "registration_campaign",
            kwargs={"campaign_slug": self.campaign.slug},
        )
        self.assertRedirects(
            response,
            redirect_url,
        )

    def test_course_with_homework_shows_workspace_and_registration_link(
        self,
    ):
        self.create_intro_homework()

        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Register")
        self.assertContains(response, "Intro")

    def test_course_page_hides_registration_button_when_registered(
        self,
    ):
        user = self.create_registered_course_user()
        self.create_intro_homework()
        self.client.force_login(user)

        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Register")

    def test_course_page_hides_registration_button_when_enrolled(self):
        user = CustomUser.objects.create_user(
            username="enrolled",
            email="enrolled@example.com",
            password="test",
        )
        Enrollment.objects.create(student=user, course=self.course)
        self.create_intro_homework()
        self.client.force_login(user)

        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Register")
