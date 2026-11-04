"""Smoke safety regressions: these tests never contact a live server."""

import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from e2e.api_client import ApiError, CmpApiClient
from e2e.config import ConfigError, load_settings


class SmokeSafetyTestCase(SimpleTestCase):
    def test_settings_refuse_live_targets_before_credentials(self):
        for target in (
            "https://courses.datatalks.club",
            "https://COURSES.DATATALKS.CLUB.:443/",
            "http://courses.datatalks.club:80",
            "https://dev.courses.datatalks.club",
            "https://unknown.example",
        ):
            with self.subTest(target=target), patch.dict(
                os.environ, {"E2E_BASE_URL": target}, clear=True
            ), patch("e2e.config._ensure_env_loaded"):
                with self.assertRaises(ConfigError):
                    load_settings()

    def test_public_base_url_fallback_cannot_select_production(self):
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://courses.datatalks.club",
        }, clear=True), patch("e2e.config._ensure_env_loaded"):
            with self.assertRaises(ConfigError):
                load_settings()

    def test_missing_target_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "e2e.config._ensure_env_loaded"
        ):
            with self.assertRaises(ConfigError):
                load_settings()

    def test_direct_api_client_refuses_production(self):
        with patch("e2e.api_client.requests.Session") as session:
            with self.assertRaises(ConfigError):
                CmpApiClient("https://courses.datatalks.club", "unused")
            session.assert_not_called()

    def test_create_course_rechecks_target_before_any_http(self):
        client = CmpApiClient("http://127.0.0.1:8000", "unused")
        client.base_url = "https://courses.datatalks.club"
        client.session = Mock()
        with self.assertRaises(ConfigError):
            client.create_course({"slug": "e2e-smoke-regression"})
        client.session.request.assert_not_called()

    def test_redirect_cannot_forward_course_post(self):
        client = CmpApiClient("http://127.0.0.1:8000", "unused")
        client.session = Mock()
        response = client.session.request.return_value
        response.status_code = 307
        response.text = "redirect"
        response.headers = {
            "Location": "https://courses.datatalks.club/api/courses/",
        }
        with self.assertRaises(ApiError):
            client.create_course({"slug": "e2e-smoke-regression"})
        self.assertIs(
            client.session.request.call_args.kwargs.get("allow_redirects"),
            False,
        )
