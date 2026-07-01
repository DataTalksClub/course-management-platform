from django.test import override_settings
from django.urls import reverse

from accounts.tests_base import (
    DATAMAILER_DISABLED_SETTINGS,
    AccountCourseTestCase,
)


@override_settings(**DATAMAILER_DISABLED_SETTINGS)
class EnrollmentProfileTestCase(AccountCourseTestCase):
    def enrollment_payload(self, display_public_profile=False):
        payload = {
            "display_name": "Student One",
            "certificate_name": "Student Certificate",
        }
        if display_public_profile:
            payload["display_public_profile"] = "on"
        return payload

    def test_account_settings_certificate_name_shows_in_enrollment_form(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("account_settings"),
            {
                "certificate_name": "Account Certificate",
                "github_url": "",
                "linkedin_url": "",
                "personal_website_url": "",
                "about_me": "",
                "dark_mode": "",
            },
        )

        self.assertRedirects(response, reverse("account_settings"))

        response = self.client.get(
            reverse("enrollment", args=[self.course.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["certificate_name"].value(),
            "Account Certificate",
        )

    def test_enrollment_form_links_to_account_public_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("enrollment", args=[self.course.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit public profile")
        self.assertContains(response, f'href="{reverse("account_settings")}"')

    def test_enrollment_certificate_name_saves_to_user_profile(self):
        self.client.force_login(self.user)
        payload = self.enrollment_payload(display_public_profile=True)
        payload["certificate_name"] = "Enrollment Certificate"

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            payload,
        )

        self.assertRedirects(response, reverse("course", args=[self.course.slug]))
        self.user.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(
            self.user.certificate_name,
            "Enrollment Certificate",
        )
        self.assertIsNone(self.enrollment.certificate_name)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["certificate_name"].value(),
            "Enrollment Certificate",
        )

    def test_enrollment_public_profile_flag_saves_enabled(self):
        self.client.force_login(self.user)
        payload = self.enrollment_payload(display_public_profile=True)

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            payload,
        )

        self.assertRedirects(response, reverse("course", args=[self.course.slug]))
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.display_public_profile)

    def test_enrollment_toggle_updates_public_profile_immediately(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_enrollment_toggle", args=[self.course.slug]),
            {"field": "display_public_profile", "value": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"field": "display_public_profile", "value": True},
        )
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.display_public_profile)

    def test_enrollment_toggle_rejects_unknown_field(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_enrollment_toggle", args=[self.course.slug]),
            {"field": "total_score", "value": "true"},
        )

        self.assertEqual(response.status_code, 400)

    def test_enrollment_public_profile_flag_saves_disabled(self):
        self.enrollment.display_public_profile = True
        self.enrollment.save()
        self.client.force_login(self.user)
        payload = self.enrollment_payload()

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            payload,
        )

        self.assertRedirects(response, reverse("course", args=[self.course.slug]))
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.display_public_profile)

    def test_leaderboard_profile_data_requires_enrollment_opt_in(self):
        self.user.github_url = "https://github.com/student"
        self.user.linkedin_url = "https://linkedin.com/in/student"
        self.user.personal_website_url = "https://student.example.com"
        self.user.about_me = "Learning data."
        self.user.save()

        response = self.client.get(
            reverse(
                "leaderboard_score_breakdown",
                args=[self.course.slug, self.enrollment.id],
            )
        )

        self.assertNotContains(response, "Learning data.")
        self.assertNotContains(response, "https://github.com/student")

        self.enrollment.display_public_profile = True
        self.enrollment.save()

        response = self.client.get(
            reverse(
                "leaderboard_score_breakdown",
                args=[self.course.slug, self.enrollment.id],
            )
        )

        self.assertContains(response, "Learning data.")
        self.assertContains(response, "https://github.com/student")
