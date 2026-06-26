import json
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from accounts.models import CustomUser, Token
from courses.models import Course, Enrollment


class DarkModeToggleTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_toggle_dark_mode_unauthenticated(self):
        """Test that unauthenticated users cannot toggle dark mode"""
        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 302)

    def test_toggle_dark_mode_authenticated(self):
        """Test that authenticated users can toggle dark mode"""
        self.client.force_login(self.user)

        self.assertFalse(self.user.dark_mode)

        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.dark_mode)

    def test_toggle_dark_mode_get_not_allowed(self):
        """Test that GET requests are not allowed"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 405)

    def test_update_account_toggle_sets_explicit_dark_mode_value(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_account_toggle"),
            {"field": "dark_mode", "value": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "field": "dark_mode",
                "value": True,
                "dark_mode": True,
            },
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

        response = self.client.post(
            reverse("update_account_toggle"),
            {"field": "dark_mode", "value": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.dark_mode)

    def test_update_account_toggle_rejects_unknown_field(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_account_toggle"),
            {"field": "is_staff", "value": "true"},
        )

        self.assertEqual(response.status_code, 400)

    def test_dark_mode_default_value(self):
        """Test that dark_mode defaults to False"""
        user = CustomUser.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='testpass123'
        )
        self.assertFalse(user.dark_mode)


@override_settings(
    DATAMAILER_URL="",
    DATAMAILER_API_KEY="",
    DATAMAILER_CLIENT="",
    DATAMAILER_AUDIENCE="",
)
class AccountSettingsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="testpass123",
        )
        self.course = Course.objects.create(
            slug="data-course",
            title="Data Course",
            description="Learn data",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Student One",
        )

    def test_account_settings_requires_login(self):
        response = self.client.get(reverse("account_settings"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(
                f"{reverse('login')}?next={reverse('account_settings')}"
            )
        )

    def test_account_settings_shows_user_and_enrolled_courses(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "Data Course")
        self.assertContains(response, "Student One")
        self.assertNotContains(response, reverse("cadmin_course_list"))

    def test_account_menu_shows_cadmin_for_staff(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("cadmin_course_list"))
        self.assertContains(response, "Course admin")

    def test_account_settings_updates_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_settings"),
            {
                "certificate_name": "Student Certificate",
                "preferred_timezone": "Europe/Berlin",
                "github_url": "https://github.com/student",
                "linkedin_url": "https://linkedin.com/in/student",
                "personal_website_url": "https://student.example.com",
                "about_me": "Learning data.",
                "dark_mode": "on",
                "email_submission_confirmations": "on",
                "email_deadline_reminders": "on",
                "email_course_updates": "on",
            },
        )

        self.assertRedirects(response, reverse("account_settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.certificate_name, "Student Certificate")
        self.assertEqual(self.user.preferred_timezone, "Europe/Berlin")
        self.assertEqual(self.user.github_url, "https://github.com/student")
        self.assertEqual(
            self.user.linkedin_url,
            "https://linkedin.com/in/student",
        )
        self.assertEqual(
            self.user.personal_website_url,
            "https://student.example.com",
        )
        self.assertEqual(self.user.about_me, "Learning data.")
        self.assertFalse(self.user.dark_mode)
        self.assertTrue(self.user.email_submission_confirmations)
        self.assertTrue(self.user.email_deadline_reminders)
        self.assertTrue(self.user.email_course_updates)

    @patch("accounts.views.update_email_preferences_for_user")
    def test_account_email_preferences_update_proxies_to_datamailer(
        self,
        update_email_preferences,
    ):
        update_email_preferences.return_value = True
        self.user.email_submission_confirmations = True
        self.user.email_deadline_reminders = True
        self.user.email_course_updates = True
        self.user.save(
            update_fields=[
                "email_submission_confirmations",
                "email_deadline_reminders",
                "email_course_updates",
            ]
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("account_email_preferences"),
            {"field": "email_deadline_reminders", "value": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "field": "email_deadline_reminders",
                "value": False,
                "datamailer_synced": True,
            },
        )
        update_email_preferences.assert_called_once_with(
            self.user,
            {"email_deadline_reminders": False},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_submission_confirmations)
        self.assertTrue(self.user.email_deadline_reminders)
        self.assertTrue(self.user.email_course_updates)

    @patch("accounts.views.get_email_preferences_for_user")
    def test_account_email_preferences_read_proxies_to_datamailer(
        self,
        get_email_preferences,
    ):
        get_email_preferences.return_value = {
            "email_submission_confirmations": False,
            "email_deadline_reminders": True,
            "email_course_updates": False,
        }
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_email_preferences"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "preferences": {
                    "email_submission_confirmations": False,
                    "email_deadline_reminders": True,
                    "email_course_updates": False,
                },
            },
        )
        get_email_preferences.assert_called_once_with(self.user)

    def test_account_email_preferences_unavailable_returns_503(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_email_preferences"))

        self.assertEqual(response.status_code, 503)

    @patch("accounts.views.get_email_preferences_for_user")
    def test_account_settings_does_not_block_on_datamailer_preferences(
        self,
        get_email_preferences,
    ):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        get_email_preferences.assert_not_called()
        self.assertNotIn("email_submission_confirmations", response.context["form"].fields)

    def test_account_settings_profile_save_preserves_toggle_preferences(self):
        self.user.dark_mode = True
        self.user.email_submission_confirmations = False
        self.user.email_deadline_reminders = False
        self.user.email_course_updates = False
        self.user.save(
            update_fields=[
                "dark_mode",
                "email_submission_confirmations",
                "email_deadline_reminders",
                "email_course_updates",
            ]
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("account_settings"),
            {
                "certificate_name": "Student Certificate",
                "github_url": "",
                "linkedin_url": "",
                "personal_website_url": "",
                "about_me": "",
            },
        )

        self.assertRedirects(response, reverse("account_settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)
        self.assertFalse(self.user.email_submission_confirmations)
        self.assertFalse(self.user.email_deadline_reminders)
        self.assertFalse(self.user.email_course_updates)

    def test_account_settings_shows_email_preference_categories(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Homework and project submissions",
        )
        self.assertContains(
            response,
            "Sends confirmation and score emails",
        )
        self.assertContains(response, "Deadline reminders")
        self.assertContains(response, "within 24 hours")
        self.assertContains(response, "one week before the deadline")
        self.assertContains(response, "one day before the deadline")
        self.assertContains(response, "links to unfinished reviews")
        self.assertContains(response, "mandatory for project completion")
        self.assertContains(response, "General course-related emails")
        self.assertContains(response, "course start announcements")

    def test_account_settings_shows_timezone_preference(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Display preferences")
        self.assertContains(response, "Deadlines and notification emails")
        self.assertContains(response, "Save display preferences")
        self.assertContains(response, "Europe/Berlin")

    def test_account_settings_shows_browser_timezone_cookie_fallback(self):
        self.client.force_login(self.user)
        self.client.cookies["browser_timezone"] = "Europe%2FBerlin"

        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Using browser timezone")
        self.assertContains(response, "Europe/Berlin")

    def test_update_timezone_preference_passive_detects_browser_timezone(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_timezone_preference"),
            data=json.dumps(
                {"timezone": "Europe/Berlin", "passive": True}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_timezone, "Europe/Berlin")

    def test_update_timezone_preference_passive_does_not_override_saved(self):
        self.user.preferred_timezone = "America/New_York"
        self.user.save(update_fields=["preferred_timezone"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_timezone_preference"),
            data=json.dumps(
                {"timezone": "Europe/Berlin", "passive": True}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_timezone, "America/New_York")

    def test_update_timezone_preference_rejects_invalid_timezone(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_timezone_preference"),
            data=json.dumps({"timezone": "Mars/Olympus"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

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
                "email_submission_confirmations": "on",
                "email_deadline_reminders": "on",
                "email_course_updates": "on",
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

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            {
                "display_name": "Student One",
                "certificate_name": "Enrollment Certificate",
                "display_public_profile": "on",
            },
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

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            {
                "display_name": "Student One",
                "certificate_name": "Student Certificate",
                "display_public_profile": "on",
            },
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

        response = self.client.post(
            reverse("enrollment", args=[self.course.slug]),
            {
                "display_name": "Student One",
                "certificate_name": "Student Certificate",
            },
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


class TokenAdminAccessTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.token_add_url = reverse("admin:accounts_token_add")
        self.student = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

    def test_non_staff_user_cannot_access_token_admin(self):
        self.client.force_login(self.student)

        response = self.client.get(self.token_add_url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Token.objects.filter(user=self.student).exists())

    def test_staff_without_token_permission_cannot_create_token(self):
        staff = CustomUser.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="password",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.post(
            self.token_add_url,
            {"key": "staff-token", "user": staff.id},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.filter(user=staff).exists())

    def test_token_admin_rejects_non_staff_user_selection(self):
        superuser = CustomUser.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        self.client.force_login(superuser)

        response = self.client.post(
            self.token_add_url,
            {
                "key": "student-token",
                "user": self.student.id,
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Token.objects.filter(user=self.student).exists())
