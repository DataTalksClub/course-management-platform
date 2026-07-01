from unittest.mock import Mock

from django.test import TestCase, override_settings

from course_management.datamailer.client import (
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
            url="https://datamailer.example.com",
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
            "timeout": 10,
            "headers": headers,
        }
        if expectation.params is not None:
            kwargs["params"] = expectation.params
        expected_url = f"https://datamailer.example.com{expectation.path}"
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
        result = getattr(client, method_case.method_name)(
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
            DATAMAILER_URL="",
            DATAMAILER_API_KEY="",
            DATAMAILER_CLIENT="",
            DATAMAILER_AUDIENCE="",
        ):
            enabled = datamailer_enabled()
            self.assertFalse(enabled)

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
        result = client.upsert_campaign(
            "course-start-2026",
            payload,
        )

        self.assertEqual(result, {"created": True})
        expectation = campaign_upsert_expectation(response, session)
        self.assert_datamailer_request(expectation)
