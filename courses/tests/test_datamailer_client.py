from dataclasses import dataclass
from unittest.mock import Mock

from django.test import TestCase, override_settings

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
    datamailer_enabled,
)


@dataclass(frozen=True)
class DatamailerRequestExpectation:
    response: Mock
    session: Mock
    method: str
    path: str
    json_payload: dict | None = None
    params: dict | None = None


@dataclass(frozen=True)
class DatamailerMethodCase:
    method_name: str
    args: tuple
    method: str
    path: str
    response_payload: dict
    expected_result: dict
    kwargs: dict | None = None
    json_payload: dict | None = None
    params: dict | None = None


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
        kwargs = {
            "json": expectation.json_payload,
            "timeout": 10,
            "headers": {
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        }
        if expectation.params is not None:
            kwargs["params"] = expectation.params
        expectation.session.request.assert_called_once_with(
            expectation.method,
            f"https://datamailer.example.com{expectation.path}",
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

    def upsert_contact_method_case(self):
        return DatamailerMethodCase(
            method_name="upsert_contact",
            args=({"email": "student@example.com"},),
            method="POST",
            path="/api/contacts",
            json_payload={"email": "student@example.com"},
            response_payload={"ok": True},
            expected_result={"ok": True},
        )

    def bulk_import_contacts_method_case(self):
        contact_import_payload = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "contacts": [{"email": "student@example.com"}],
        }
        return DatamailerMethodCase(
            method_name="bulk_import_contacts",
            args=(contact_import_payload,),
            method="POST",
            path="/api/contacts/imports",
            json_payload=contact_import_payload,
            response_payload={"counts": {"created": 1}},
            expected_result={"counts": {"created": 1}},
        )

    def erase_contact_method_case(self):
        erase_payload = {
            "email": "student@example.com",
            "audience": "dtc-courses",
            "client": "dtc-courses",
        }
        return DatamailerMethodCase(
            method_name="erase_contact",
            args=("student@example.com",),
            method="POST",
            path="/api/contacts/erase",
            json_payload=erase_payload,
            response_payload={"erased": True},
            expected_result={"erased": True},
        )

    def contact_write_method_cases(self):
        cases = []

        upsert_case = self.upsert_contact_method_case()
        cases.append(upsert_case)

        import_case = self.bulk_import_contacts_method_case()
        cases.append(import_case)

        erase_case = self.erase_contact_method_case()
        cases.append(erase_case)

        return cases

    def contact_status_method_case(self):
        params = {
            "email": "student@example.com",
            "audience": "dtc-courses",
            "client": "dtc-courses",
        }
        return DatamailerMethodCase(
            method_name="contact_status",
            args=("student@example.com",),
            method="GET",
            path="/api/contacts/status",
            params=params,
            response_payload={"exists": True},
            expected_result={"exists": True},
        )

    def contact_history_method_case(self):
        params = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "limit": 5,
        }
        return DatamailerMethodCase(
            method_name="contact_history",
            args=(42,),
            kwargs={"limit": 5},
            method="GET",
            path="/api/contacts/42/history",
            params=params,
            response_payload={"transactional_messages": []},
            expected_result={"transactional_messages": []},
        )

    def contact_read_method_cases(self):
        cases = []
        case = self.contact_status_method_case()
        cases.append(case)
        case = self.contact_history_method_case()
        cases.append(case)
        return cases

    def contact_method_cases(self):
        cases = []
        for case in self.contact_write_method_cases():
            cases.append(case)
        for case in self.contact_read_method_cases():
            cases.append(case)
        return cases

    def recipient_list_member_write_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="upsert_recipient_list_member",
                args=(
                    "ml-zoomcamp-2026",
                    "registration:42",
                    {"email": "student@example.com"},
                ),
                method="PUT",
                path="/api/recipient-lists/ml-zoomcamp-2026/members/registration:42",
                json_payload={"email": "student@example.com"},
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
            DatamailerMethodCase(
                method_name="remove_recipient_list_member",
                args=("ml-zoomcamp-2026", "registration:42"),
                method="DELETE",
                path="/api/recipient-lists/ml-zoomcamp-2026/members/registration:42",
                json_payload={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                },
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
        ]

    def recipient_list_member_read_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="recipient_list_members",
                args=("ml-zoomcamp-2026:@e",),
                kwargs={"limit": 500},
                method="GET",
                path="/api/recipient-lists/ml-zoomcamp-2026:@e/members",
                params={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                    "include_removed": "false",
                    "limit": 500,
                },
                response_payload={"members": []},
                expected_result={"members": []},
            ),
        ]

    def recipient_list_member_method_cases(self):
        cases = []
        for case in self.recipient_list_member_write_method_cases():
            cases.append(case)
        for case in self.recipient_list_member_read_method_cases():
            cases.append(case)
        return cases

    def recipient_list_import_payload(self):
        return {
            "source_url": "https://storage.example.com/import.jsonl",
            "idempotency_key": "cmp-import-1",
        }

    def create_recipient_list_import_method_case(self):
        import_payload = self.recipient_list_import_payload()
        json_payload = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "source_url": "https://storage.example.com/import.jsonl",
            "idempotency_key": "cmp-import-1",
        }
        return DatamailerMethodCase(
            method_name="create_recipient_list_import",
            args=("ml-zoomcamp-2026:@e", import_payload),
            method="POST",
            path="/api/recipient-lists/ml-zoomcamp-2026:@e/imports",
            json_payload=json_payload,
            response_payload={"ok": True},
            expected_result={"ok": True},
        )

    def recipient_list_import_status_method_case(self):
        params = {"audience": "dtc-courses", "client": "dtc-courses"}
        return DatamailerMethodCase(
            method_name="recipient_list_import",
            args=("ml-zoomcamp-2026:@e", 42),
            method="GET",
            path="/api/recipient-lists/ml-zoomcamp-2026:@e/imports/42",
            params=params,
            response_payload={"ok": True},
            expected_result={"ok": True},
        )

    def recipient_list_import_method_cases(self):
        cases = []
        case = self.create_recipient_list_import_method_case()
        cases.append(case)
        case = self.recipient_list_import_status_method_case()
        cases.append(case)
        return cases

    def transient_transactional_payload(self):
        member = {"email": "learner@example.com"}
        members = []
        members.append(member)
        return {
            "template_key": "deadline-reminder",
            "members": members,
        }

    def recipient_list_transactional_send_method_case(self):
        payload = {"template_key": "homework-score-notification"}
        return DatamailerMethodCase(
            method_name="send_recipient_list_transactional",
            args=(
                "ml-zoomcamp-2026:@e:@homework:homework-1",
                payload,
            ),
            method="POST",
            path=(
                "/api/recipient-lists/"
                "ml-zoomcamp-2026:@e:@homework:homework-1"
                "/transactional-send"
            ),
            json_payload=payload,
            response_payload={"ok": True},
            expected_result={"ok": True},
        )

    def transient_transactional_send_method_case(self):
        transient_payload = self.transient_transactional_payload()
        return DatamailerMethodCase(
            method_name="send_transient_recipient_list_transactional",
            args=(transient_payload,),
            method="POST",
            path="/api/transient-recipient-lists/transactional-send",
            json_payload=transient_payload,
            response_payload={"ok": True},
            expected_result={"ok": True},
        )

    def transactional_send_method_cases(self):
        cases = []
        case = self.recipient_list_transactional_send_method_case()
        cases.append(case)
        case = self.transient_transactional_send_method_case()
        cases.append(case)
        return cases

    def campaign_upsert_payload(self):
        return {
            "subject": "Course starts tomorrow",
            "html_body": "<p>Hello</p>",
            "text_body": "Hello",
        }

    def campaign_upsert_expected_payload(self):
        payload = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
        }
        upsert_payload = self.campaign_upsert_payload()
        payload.update(upsert_payload)
        return payload

    def campaign_upsert_expectation(self, response, session):
        expected_payload = self.campaign_upsert_expected_payload()
        return DatamailerRequestExpectation(
            response=response,
            session=session,
            method="PUT",
            path="/api/campaigns/course-start-2026",
            json_payload=expected_payload,
        )

    def recipient_list_method_cases(self):
        cases = []
        for case in self.recipient_list_member_method_cases():
            cases.append(case)
        for case in self.recipient_list_import_method_cases():
            cases.append(case)
        return cases

    def transactional_status_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="transactional_message_status",
                args=(42,),
                method="GET",
                path="/api/transactional/messages/42",
                response_payload={"message": {"id": 42}},
                expected_result={"message": {"id": 42}},
            ),
        ]

    def transactional_method_cases(self):
        cases = []
        for case in self.transactional_status_method_cases():
            cases.append(case)
        for case in self.transactional_send_method_cases():
            cases.append(case)
        return cases

    def campaign_read_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="campaign",
                args=("course-start-2026",),
                method="GET",
                path="/api/campaigns/course-start-2026",
                params={"audience": "dtc-courses", "client": "dtc-courses"},
                response_payload={
                    "campaign": {"external_key": "course-start-2026"}
                },
                expected_result={
                    "campaign": {"external_key": "course-start-2026"}
                },
            ),
            DatamailerMethodCase(
                method_name="preview_campaign",
                args=("course-start-2026",),
                method="POST",
                path="/api/campaigns/course-start-2026/preview",
                json_payload={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                },
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
        ]

    def campaign_control_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="queue_campaign",
                args=("course-start-2026",),
                method="POST",
                path="/api/campaigns/course-start-2026/queue",
                json_payload={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                },
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
            DatamailerMethodCase(
                method_name="cancel_campaign",
                args=("course-start-2026",),
                method="POST",
                path="/api/campaigns/course-start-2026/cancel",
                json_payload={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                },
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
        ]

    def campaign_send_method_cases(self):
        return [
            DatamailerMethodCase(
                method_name="test_send_campaign",
                args=("course-start-2026", ["test@example.com"]),
                method="POST",
                path="/api/campaigns/course-start-2026/test-send",
                json_payload={
                    "audience": "dtc-courses",
                    "client": "dtc-courses",
                    "emails": ["test@example.com"],
                },
                response_payload={"ok": True},
                expected_result={"ok": True},
            ),
        ]

    def campaign_method_cases(self):
        cases = []
        for case in self.campaign_read_method_cases():
            cases.append(case)
        for case in self.campaign_control_method_cases():
            cases.append(case)
        for case in self.campaign_send_method_cases():
            cases.append(case)
        return cases

    def datamailer_method_cases(self):
        cases = []
        for case in self.contact_method_cases():
            cases.append(case)
        for case in self.recipient_list_method_cases():
            cases.append(case)
        for case in self.transactional_method_cases():
            cases.append(case)
        for case in self.campaign_method_cases():
            cases.append(case)
        return cases

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
        cases = self.datamailer_method_cases()
        for case in cases:
            with self.subTest(method_name=case.method_name):
                self.assert_datamailer_method_case(case)

    def test_campaign_upsert_uses_expected_endpoint_and_scope(self):
        session, response = self.datamailer_session(
            payload={"created": True}
        )
        config = self.datamailer_config()
        client = DatamailerClient(config, session=session)

        upsert_payload = self.campaign_upsert_payload()
        result = client.upsert_campaign(
            "course-start-2026",
            upsert_payload,
        )

        self.assertEqual(result, {"created": True})
        expectation = self.campaign_upsert_expectation(response, session)
        self.assert_datamailer_request(expectation)
