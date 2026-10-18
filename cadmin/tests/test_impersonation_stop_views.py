import re

from django.test import Client
from django.urls import reverse

from .impersonation_base import (
    ImpersonationCadminViewTestBase,
    admin_credentials,
)


CSRF_INPUT_RE = re.compile(
    rb'name="csrfmiddlewaretoken"\s+value="([^"]+)"'
)


def csrf_token_from(response):
    match = CSRF_INPUT_RE.search(response.content)
    assert match is not None, "no csrfmiddlewaretoken input in response"
    return match.group(1).decode()


class ImpersonationBannerCadminViewTests(
    ImpersonationCadminViewTestBase
):
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

    def test_stop_impersonating_requires_post(self):
        self.client.login(**admin_credentials)

        response = self.client.get(reverse("stop_impersonating"))

        self.assertEqual(response.status_code, 405)


class StopImpersonatingCsrfCadminViewTests(
    ImpersonationCadminViewTestBase
):
    """stop_impersonating must stay CSRF-protected.

    Django rotates the CSRF token on every login, including the loginas
    switch, so a stop form rendered before a switch carries a stale token.
    The view must reject missing and stale tokens while accepting the
    token rendered by the current impersonation banner.
    """

    def impersonate_with_csrf(self, client):
        """Run the loginas switch under CSRF enforcement."""
        login_url = self.login_as_user_url()
        course_list_url = reverse("course_list")

        response = client.get(course_list_url)
        self.assertEqual(response.status_code, 200)
        token = client.cookies["csrftoken"].value

        response = client.post(
            login_url, {"csrfmiddlewaretoken": token}
        )
        self.assertEqual(response.status_code, 302)
        return token

    def test_stop_impersonating_rejects_post_without_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(**admin_credentials)
        self.impersonate_with_csrf(csrf_client)

        response = csrf_client.post(reverse("stop_impersonating"))

        self.assertEqual(response.status_code, 403)
        response = csrf_client.get(reverse("course_list"))
        self.assertEqual(response.wsgi_request.user, self.user)
        self.assertContains(response, "impersonation-banner")

    def test_stop_impersonating_accepts_fresh_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(**admin_credentials)
        self.impersonate_with_csrf(csrf_client)

        course_list_url = reverse("course_list")
        response = csrf_client.get(course_list_url)
        self.assertContains(response, "impersonation-banner")
        self.assertEqual(response.wsgi_request.user, self.user)
        token = csrf_token_from(response)

        response = csrf_client.post(
            reverse("stop_impersonating"),
            {"csrfmiddlewaretoken": token},
        )

        self.assertRedirects(response, reverse("cadmin_course_list"))
        response = csrf_client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.admin_user)
        self.assertNotContains(response, "impersonation-banner")

    def test_stop_impersonating_rejects_stale_csrf_token_after_user_switch(
        self,
    ):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(**admin_credentials)
        stale_token = self.impersonate_with_csrf(csrf_client)

        course_list_url = reverse("course_list")
        stop_url = reverse("stop_impersonating")
        response = csrf_client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.user)

        response = csrf_client.post(
            stop_url,
            {"csrfmiddlewaretoken": stale_token},
        )

        self.assertEqual(response.status_code, 403)

        # Staff recovers by reloading the page and submitting its token.
        response = csrf_client.get(course_list_url)
        fresh_token = csrf_token_from(response)
        response = csrf_client.post(
            stop_url,
            {"csrfmiddlewaretoken": fresh_token},
        )
        self.assertRedirects(response, reverse("cadmin_course_list"))
        response = csrf_client.get(course_list_url)
        self.assertEqual(response.wsgi_request.user, self.admin_user)
