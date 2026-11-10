from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse

from course_management.datamailer.payloads.email_campaigns import (
    email_campaign_datamailer_payload,
)
from course_management.datamailer.payloads.urls import unsubscribe_url_template

RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "secret-token",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
}
TOKEN = "abcDEF123_-token"
POST_TARGET = "accounts.views.unsubscribe.requests.post"


def relay_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    return response


@override_settings(**RELAY_SETTINGS)
class UnsubscribeViewTestCase(TestCase):
    def url(self, token=TOKEN):
        return reverse("account_unsubscribe", kwargs={"token": token})

    @patch(POST_TARGET)
    def test_get_shows_confirmation_and_does_not_unsubscribe(self, post):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsubscribe</button>")
        post.assert_not_called()

    @patch(POST_TARGET, return_value=relay_response(204))
    def test_one_click_post_forwards_token_to_relay(self, post):
        response = self.client.post(
            self.url(), {"List-Unsubscribe": "One-Click"}
        )

        self.assertEqual(response.status_code, 204)
        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0],
            f"https://relay.example.com/unsubscribe/{TOKEN}",
        )
        self.assertEqual(
            post.call_args.kwargs["data"], {"List-Unsubscribe": "One-Click"}
        )

    @patch(POST_TARGET, return_value=relay_response(200))
    def test_confirm_page_post_shows_confirmation(self, post):
        response = self.client.post(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have been unsubscribed")

    @patch(POST_TARGET, return_value=relay_response(404))
    def test_unknown_token_is_404_not_success(self, post):
        response = self.client.post(self.url())

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "invalid or has expired", status_code=404)

    @patch(POST_TARGET)
    def test_malformed_token_never_reaches_relay(self, post):
        response = self.client.post(self.url("bad token%2F..%2Fx"))

        self.assertEqual(response.status_code, 404)
        post.assert_not_called()

    @patch(POST_TARGET, side_effect=requests.ConnectionError("down"))
    def test_relay_outage_is_loud_and_never_reports_success(self, post):
        with self.assertLogs("accounts.views.unsubscribe", "ERROR") as logs:
            one_click = self.client.post(
                self.url(), {"List-Unsubscribe": "One-Click"}
            )
            page = self.client.post(self.url())

        self.assertEqual(one_click.status_code, 503)
        self.assertEqual(one_click["Retry-After"], "60")
        self.assertEqual(page.status_code, 503)
        self.assertNotContains(
            page, "You have been unsubscribed", status_code=503
        )
        self.assertTrue(
            any("cmp_unsubscribe_failed" in line for line in logs.output)
        )

    @patch(POST_TARGET, return_value=relay_response(500))
    def test_relay_error_status_is_503(self, post):
        with self.assertLogs("accounts.views.unsubscribe", "ERROR"):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 503)

    @override_settings(RELAY_URL="", RELAY_API_KEY="")
    @patch(POST_TARGET)
    def test_missing_relay_config_is_503(self, post):
        with self.assertLogs("accounts.views.unsubscribe", "ERROR"):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 503)
        post.assert_not_called()


@override_settings(PUBLIC_BASE_URL="https://courses.example.com")
class UnsubscribeUrlTemplateTestCase(TestCase):
    def test_template_points_at_cmp_with_token_placeholder(self):
        self.assertEqual(
            unsubscribe_url_template(),
            "https://courses.example.com/accounts/unsubscribe/{token}/",
        )

    def test_email_campaign_payload_carries_cmp_unsubscribe_template(self):
        email_campaign = SimpleNamespace(
            pk=1,
            subject="Course starts",
            preview_text="",
            body_markdown="Hello",
            registration_campaign=SimpleNamespace(
                slug="ml-2026", current_course_id=None
            ),
        )

        payload = email_campaign_datamailer_payload(email_campaign)

        self.assertEqual(
            payload["unsubscribe_url_template"],
            "https://courses.example.com/accounts/unsubscribe/{token}/",
        )
