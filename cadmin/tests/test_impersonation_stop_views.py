from django.test import Client
from django.urls import reverse

from .impersonation_base import (
    ImpersonationCadminViewTestBase,
    admin_credentials,
)


class ImpersonationBannerCadminViewTests(ImpersonationCadminViewTestBase):
    def test_impersonation_banner_shown_when_logged_in_as_student(self):
        login_url = self.login_as_user_url()
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


class StopImpersonatingCadminViewTests(ImpersonationCadminViewTestBase):
    def test_stop_impersonating_restores_admin_account(self):
        login_url = self.login_as_user_url()
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


class StopImpersonatingCsrfCadminViewTests(ImpersonationCadminViewTestBase):
    def test_stop_impersonating_allows_stale_csrf_token_after_user_switch(
        self,
    ):
        csrf_client = Client(enforce_csrf_checks=True)
        login_url = self.login_as_user_url()
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
