from unittest.mock import Mock

from django.test import TestCase, override_settings

from course_management.datamailer.client import (
    DEFAULT_TIMEOUT_SECONDS,
    DatamailerClient,
    DatamailerConfig,
    datamailer_enabled,
)
from courses.tests.datamailer_client_cases import (
    DatamailerRequestExpectation,
    campaign_upsert_expectation,
    campaign_upsert_payload,
    datamailer_method_cases,
)


class DatamailerClientEndpointTest(TestCase):
    def datamailer_config(self):
        return DatamailerConfig(
            url="https://relay.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

    def datamailer_session(self, payload=None):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = payload or {"ok": True}
        session.request.return_value = response
        return session, response

    def assert_datamailer_request(self, expectation):
        headers = {
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
        }
        kwargs = {
            "json": expectation.json_payload,
            "timeout": DEFAULT_TIMEOUT_SECONDS,
            "headers": headers,
        }
        if expectation.params is not None:
            kwargs["params"] = expectation.params
        expected_url = f"https://relay.example.com{expectation.path}"
        expectation.session.request.assert_called_once_with(
            expectation.method,
            expected_url,
            **kwargs,
        )
        expectation.response.raise_for_status.assert_called_once()

    def assert_datamailer_method_case(self, method_case):
        session, response = self.datamailer_session(
            payload=method_case.response_payload
        )
        config = self.datamailer_config()
        client = DatamailerClient(config, session=session)

        kwargs = method_case.kwargs or {}
        endpoint = client
        for endpoint_part in method_case.endpoint_name.split("."):
            endpoint = getattr(endpoint, endpoint_part)
        method = getattr(endpoint, method_case.method_name)
        result = method(
            *method_case.args,
            **kwargs,
        )

        self.assertEqual(result, method_case.expected_result)
        expectation = DatamailerRequestExpectation(
            response=response,
            session=session,
            method=method_case.method,
            path=method_case.path,
            json_payload=method_case.json_payload,
            params=method_case.params,
        )
        self.assert_datamailer_request(expectation)

    def test_missing_env_disables_datamailer(self):
        with override_settings(
            RELAY_URL="",
            RELAY_API_KEY="",
            RELAY_CLIENT="",
            RELAY_AUDIENCE="",
        ):
            enabled = datamailer_enabled()
            self.assertFalse(enabled)

    @override_settings(
        RELAY_URL="https://relay.example.com",
        RELAY_API_KEY="relay-token",
        RELAY_CLIENT="dtc-courses",
        RELAY_AUDIENCE="dtc-courses",
        RELAY_FROM_EMAIL="courses",
        RELAY_STRICT=True,
    )
    def test_relay_settings_configure_client(self):
        config = DatamailerConfig.from_settings()

        self.assertIsNotNone(config)
        self.assertEqual(config.url, "https://relay.example.com")
        self.assertEqual(config.api_key, "relay-token")
        self.assertEqual(config.client, "dtc-courses")
        self.assertEqual(config.audience, "dtc-courses")
        self.assertEqual(config.from_email, "courses")
        self.assertTrue(config.strict)

    @override_settings(
        RELAY_URL="",
        RELAY_API_KEY="",
        RELAY_CLIENT="",
        RELAY_AUDIENCE="",
        DATAMAILER_URL="https://datamailer.example.com",
        DATAMAILER_API_KEY="legacy-token",
        DATAMAILER_CLIENT="dtc-courses",
        DATAMAILER_AUDIENCE="dtc-courses",
    )
    def test_legacy_datamailer_settings_do_not_configure_client(self):
        self.assertFalse(datamailer_enabled())

    def test_client_methods_use_expected_endpoints_and_scope(self):
        cases = datamailer_method_cases()
        for case in cases:
            with self.subTest(method_name=case.method_name):
                self.assert_datamailer_method_case(case)

    def test_campaign_upsert_uses_expected_endpoint_and_scope(self):
        session, response = self.datamailer_session(
            payload={"created": True}
        )
        config = self.datamailer_config()
        client = DatamailerClient(config, session=session)

        payload = campaign_upsert_payload()
        result = client.campaigns.upsert_campaign(
            "course-start-2026",
            payload,
        )

        self.assertEqual(result, {"created": True})
        expectation = campaign_upsert_expectation(response, session)
        self.assert_datamailer_request(expectation)
