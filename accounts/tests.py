from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import CustomUser
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

    def test_dark_mode_default_value(self):
        """Test that dark_mode defaults to False"""
        user = CustomUser.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='testpass123'
        )
        self.assertFalse(user.dark_mode)


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
                "github_url": "https://github.com/student",
                "linkedin_url": "https://linkedin.com/in/student",
                "personal_website_url": "https://student.example.com",
                "about_me": "Learning data.",
                "dark_mode": "on",
            },
        )

        self.assertRedirects(response, reverse("account_settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.certificate_name, "Student Certificate")
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
        self.assertTrue(self.user.dark_mode)

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
