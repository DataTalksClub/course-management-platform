import json
from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.client_chunking import MAX_REQUEST_BODY_BYTES
from course_management.datamailer.client_pacing import DatabaseRelayPacer


def member(index):
    return {
        "source_object_key": f"user:{index}",
        "email": f"learner-{index}@example.com",
        "status": "active",
        "metadata": {"user_id": index},
    }


def bulk_upsert_payload(members):
    return {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "list": {"type": "registrants", "name": "Course registrants"},
        "members": members,
    }


def transient_send_payload(members):
    return {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "template_key": "deadline-reminder",
        "idempotency_key": "deadline-reminders:hw-1:24h",
        "context": {"course_title": "ML Zoomcamp"},
        "list": {
            "key": "ml-zoomcamp-2026:@e:@homework:hw-1",
            "name": "HW 1 submitters",
            "metadata": {},
        },
        "members": members,
    }


class WafSession:
    """Fake requests session that rejects bodies over the WAF body limit."""

    def __init__(self, response_for_chunk):
        self.request_bodies = []
        self.response_for_chunk = response_for_chunk

    def request(self, method, url, **kwargs):
        body = json.dumps(kwargs["json"])
        self.request_bodies.append(body)
        if len(body.encode()) > 8192:
            error = requests.HTTPError("403 Client Error: Forbidden for url")
            error.response = None
            raise error
        return self.response_for_chunk(kwargs["json"])


def json_response(payload):
    response = Mock_response()
    response.json.return_value = payload
    return response


def Mock_response():
    from unittest.mock import Mock

    response = Mock(content=b"{}")
    response.raise_for_status.return_value = None
    return response


class BulkUpsertChunkingTest(SimpleTestCase):
    def setUp(self):
        self.clock = 0.0
        self.addCleanup(patch.stopall)
        patch("time.monotonic", side_effect=lambda: self.clock).start()
        patch("time.sleep", side_effect=self.advance_clock).start()

    def advance_clock(self, seconds):
        self.clock += seconds

    def config(self):
        return DatamailerConfig(
            url="https://relay.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

    def test_bulk_upsert_large_member_list_is_chunked_under_waf_limit(self):
        members = [member(i) for i in range(200)]
        session = WafSession(
            lambda chunk: json_response(
                {
                    "recipient_list": {"key": "course-2026"},
                    "created_count": len(chunk["members"]),
                    "updated_count": 0,
                }
            )
        )
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.members.bulk_upsert(
            "course-2026",
            bulk_upsert_payload(members),
        )

        self.assertGreater(len(session.request_bodies), 1)
        for body in session.request_bodies:
            self.assertLessEqual(len(body.encode()), MAX_REQUEST_BODY_BYTES)
        self.assertEqual(response["created_count"], 200)
        self.assertEqual(response["updated_count"], 0)
        sent_members = sum(
            len(json.loads(body)["members"]) for body in session.request_bodies
        )
        self.assertEqual(sent_members, 200)

    def test_bulk_upsert_small_payload_sends_single_unchanged_request(self):
        payload = bulk_upsert_payload([member(i) for i in range(5)])
        seen = {}

        def respond(chunk):
            seen.update(chunk)
            return json_response(
                {"recipient_list": {"key": "course-2026"}, "created_count": 5, "updated_count": 2}
            )

        session = WafSession(respond)
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.members.bulk_upsert(
            "course-2026", payload
        )

        self.assertEqual(len(session.request_bodies), 1)
        self.assertEqual(seen, payload)
        self.assertEqual(response["created_count"], 5)
        self.assertEqual(response["updated_count"], 2)

    def test_transient_send_submits_all_members_in_one_request(self):
        members = [member(i) for i in range(150)]
        seen = []

        def respond(payload):
            seen.append(payload)
            return json_response(
                {
                    "transient_recipient_list": {
                        "key": "transient-list",
                        "name": "HW 1 submitters",
                        "member_count": len(payload["members"]),
                        "active_member_count": len(payload["members"]),
                    },
                    "template_key": "deadline-reminder",
                    "idempotency_key": "deadline-reminders:hw-1:24h",
                    "created_count": len(payload["members"]),
                    "enqueued_count": len(payload["members"]) - 1,
                    "skipped_count": 1,
                    "idempotent_replay_count": 0,
                }
            )

        class RecordingSession:
            def __init__(self):
                self.request_bodies = []

            def request(self, method, url, **kwargs):
                self.request_bodies.append(json.dumps(kwargs["json"]))
                return respond(kwargs["json"])

        session = RecordingSession()
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.sends.send_to_transient_list(
            transient_send_payload(members)
        )

        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]["members"]), 150)
        self.assertEqual(response["created_count"], 150)
        self.assertEqual(response["enqueued_count"], 149)
        self.assertEqual(response["skipped_count"], 1)

    def test_transient_send_small_payload_sends_single_unchanged_request(self):
        payload = transient_send_payload([member(i) for i in range(5)])
        seen = {}

        def respond(chunk):
            seen.update(chunk)
            return json_response(
                {
                    "transient_recipient_list": {
                        "key": "transient-list",
                        "member_count": 5,
                        "active_member_count": 5,
                    },
                    "created_count": 5,
                    "enqueued_count": 5,
                    "skipped_count": 0,
                    "idempotent_replay_count": 0,
                }
            )

        session = WafSession(respond)
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.sends.send_to_transient_list(payload)

        self.assertEqual(len(session.request_bodies), 1)
        self.assertEqual(seen, payload)
        self.assertEqual(response["enqueued_count"], 5)

    def test_edge_errors_remain_visible_without_blind_retries(self):
        def reject(chunk):
            raise requests.HTTPError("403: forbidden")

        session = WafSession(reject)
        client = DatamailerClient(self.config(), session=session)
        with self.assertRaisesMessage(requests.HTTPError, "403: forbidden"):
            client.recipient_lists.sends.send_to_transient_list(
                transient_send_payload([member(1)])
            )
        self.assertEqual(len(session.request_bodies), 1)

    def test_client_retries_cloudfront_403_429_and_5xx_when_enabled(self):
        cf_403 = Mock(
            status_code=403,
            headers={"Server": "CloudFront", "Content-Type": "text/html"},
            text="<html>403 ERROR The request could not be satisfied.</html>",
        )
        cf_403.raise_for_status.side_effect = requests.HTTPError(
            "403 Forbidden", response=cf_403
        )
        rate_429 = Mock(
            status_code=429,
            headers={"Retry-After": "5"},
            text="Too Many Requests",
        )
        rate_429.raise_for_status.side_effect = requests.HTTPError(
            "429 Too Many Requests", response=rate_429
        )
        err_504 = Mock(status_code=504, headers={}, text="Gateway Timeout")
        err_504.raise_for_status.side_effect = requests.HTTPError(
            "504 Gateway Timeout", response=err_504
        )
        ok_200 = json_response({"ok": True})

        attempts = [cf_403, rate_429, err_504, ok_200]
        session = Mock()
        session.request.side_effect = attempts
        client = DatamailerClient(self.config(), session=session, max_retries=3)

        result = client.contacts.upsert_contact({"email": "a@example.com"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(session.request.call_count, 4)


class DatabaseRelayPacerTest(TestCase):
    def test_database_pacer_allows_burst_then_paces(self):
        pacer = DatabaseRelayPacer(
            key="test_pacer",
            budget=180,
            window=300.0,
            burst=3,
        )
        base_now = timezone.now()
        with patch(
            "course_management.datamailer.client_pacing.timezone.now",
            return_value=base_now,
        ), patch("course_management.datamailer.client_pacing.time.sleep") as sleep_mock:
            self.assertEqual(pacer.reserve_slot(), 0.0)
            self.assertEqual(pacer.reserve_slot(), 0.0)
            self.assertEqual(pacer.reserve_slot(), 0.0)
            wait = pacer.reserve_slot()
            self.assertGreater(wait, 1.5)
            sleep_mock.assert_called_once()
