from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course, Enrollment, User


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)

admin_credentials = dict(
    username="admin@test.com",
    password="admin123",
)


class ImpersonationCadminViewTests(TestCase):
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

    def test_log_as_user_requires_post_request(self):
        """Test that the log as user endpoint requires a POST request"""
        url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_log_as_user_with_post_request(self):
        """Test that staff can log in as another user with POST request"""
        Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )

        self.client.login(**admin_credentials)
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.admin_user.id),
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_impersonation_banner_shown_when_logged_in_as_student(self):
        login_url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )
        course_list_url = reverse("course_list")
        stop_url = reverse("stop_impersonating")

        self.client.login(**admin_credentials)
        response = self.client.post(login_url)

        self.assertEqual(response.status_code, 302)
        response = self.client.get(course_list_url)

        self.assertContains(response, "impersonation-banner")
        self.assertContains(
            response,
            f"You are logged in as <strong>{self.user.email}</strong>",
            html=True,
        )
        self.assertContains(response, "Return to admin account")
        self.assertContains(response, stop_url)

    def test_stop_impersonating_restores_admin_account(self):
        login_url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )
        course_list_url = reverse("course_list")
        stop_url = reverse("stop_impersonating")
        cadmin_course_list_url = reverse("cadmin_course_list")

        self.client.login(**admin_credentials)
        self.client.post(login_url)

        response = self.client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.user)

        response = self.client.post(stop_url)

        self.assertRedirects(response, cadmin_course_list_url)
        response = self.client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.admin_user)
        self.assertNotContains(response, "impersonation-banner")

    def test_stop_impersonating_allows_stale_csrf_token_after_user_switch(
        self,
    ):
        csrf_client = Client(enforce_csrf_checks=True)
        login_url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )
        course_list_url = reverse("course_list")
        stop_url = reverse("stop_impersonating")
        cadmin_course_list_url = reverse("cadmin_course_list")

        csrf_client.login(**admin_credentials)
        response = csrf_client.get(course_list_url)
        self.assertEqual(response.status_code, 200)
        admin_csrf_token = csrf_client.cookies["csrftoken"].value

        csrf_payload = {"csrfmiddlewaretoken": admin_csrf_token}
        response = csrf_client.post(login_url, csrf_payload)
        self.assertEqual(response.status_code, 302)

        response = csrf_client.get(course_list_url)
        self.assertContains(response, "impersonation-banner")
        self.assertEqual(response.wsgi_request.user, self.user)

        response = csrf_client.post(stop_url, csrf_payload)

        self.assertRedirects(response, cadmin_course_list_url)
        response = csrf_client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.admin_user)

    def test_staff_cannot_impersonate_other_staff(self):
        """Test that staff users cannot impersonate other staff users"""
        other_staff = User.objects.create_user(
            username="staff2@test.com",
            email="staff2@test.com",
            password="staff123",
            is_staff=True,
        )
        url = reverse(
            "loginas-user-login",
            kwargs={"user_id": other_staff.id},
        )

        self.client.login(**admin_credentials)
        response = self.client.post(url, follow=True)

        self.assertEqual(
            response.wsgi_request.user.username, "admin@test.com"
        )

    def test_enrollment_edit_has_login_as_button(self):
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        url = reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )
        login_url = reverse(
            "loginas-user-login",
            kwargs={"user_id": self.user.id},
        )
        course_url = reverse(
            "course",
            kwargs={"course_slug": self.course.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in as student")
        self.assertContains(response, login_url)
        self.assertContains(response, f'value="{course_url}"')
