import json

import requests
from django.test import SimpleTestCase
from unittest.mock import patch

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.client_chunking import MAX_REQUEST_BODY_BYTES


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


class RelayListSession:
    """Fake Relay list: rejects oversized bodies, tracks active members."""

    def __init__(self, active_keys, has_more=False):
        self.active = {key: {"source_object_key": key} for key in active_keys}
        self.has_more = has_more
        self.calls = []

    def request(self, method, url, **kwargs):
        body = json.dumps(kwargs.get("json"))
        self.calls.append((method, url))
        if len(body.encode()) > 8192:
            raise requests.HTTPError("403 Client Error: Forbidden for url")
        if url.endswith("/members/reconcile"):
            members = kwargs["json"]["members"]
            keys = {m["source_object_key"] for m in members}
            removed = [k for k in self.active if k not in keys]
            self.active = {k: {"source_object_key": k} for k in keys}
            return json_response({"upsert_count": len(keys), "removed_count": len(removed)})
        if url.endswith("/members/bulk-upsert"):
            for m in kwargs["json"]["members"]:
                self.active[m["source_object_key"]] = {"source_object_key": m["source_object_key"]}
            return json_response(
                {"recipient_list": {"key": "course-2026", "active_member_count": len(self.active)}}
            )
        if method == "GET":
            members = [m | {"status": "active"} for m in self.active.values()]
            return json_response({"members": members, "has_more": self.has_more})
        if method == "DELETE":
            self.active.pop(url.rsplit("/", 1)[1])
            return json_response({"status": "removed"})
        raise AssertionError(f"unexpected {method} {url}")


class ReconcileChunkingTest(SimpleTestCase):
    setUp = BulkUpsertChunkingTest.setUp
    advance_clock = BulkUpsertChunkingTest.advance_clock
    config = BulkUpsertChunkingTest.config

    def test_large_reconcile_is_chunked_and_removes_stale_members(self):
        members = [member(i) for i in range(200)]
        session = RelayListSession(["user:0", "user:1", "registration:42658", "registration:40808"])
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.members.reconcile(
            "course-2026:@approved", bulk_upsert_payload(members)
        )

        self.assertEqual(set(session.active), {f"user:{i}" for i in range(200)})
        self.assertEqual(response["removed_count"], 2)
        self.assertEqual(response["upsert_count"], 200)
        self.assertEqual(response["recipient_list"]["active_member_count"], 200)
        self.assertNotIn(
            "POST", {m for m, url in session.calls if url.endswith("/reconcile")}
        )
        deleted = sorted(url.rsplit("/", 1)[1] for m, url in session.calls if m == "DELETE")
        self.assertEqual(deleted, ["registration:40808", "registration:42658"])

    def test_large_reconcile_refuses_partial_listing(self):
        session = RelayListSession(["stale:1"], has_more=True)
        client = DatamailerClient(self.config(), session=session)

        with self.assertRaises(RuntimeError):
            client.recipient_lists.members.reconcile(
                "course-2026:@approved",
                bulk_upsert_payload([member(i) for i in range(200)]),
            )
        self.assertIn("stale:1", session.active)
        self.assertFalse([c for c in session.calls if c[0] == "DELETE"])

    def test_small_reconcile_uses_single_relay_reconcile_call(self):
        session = RelayListSession(["user:0", "stale:1"])
        client = DatamailerClient(self.config(), session=session)

        response = client.recipient_lists.members.reconcile(
            "course-2026:@approved", bulk_upsert_payload([member(0)])
        )

        self.assertEqual(len(session.calls), 1)
        self.assertTrue(session.calls[0][1].endswith("/members/reconcile"))
        self.assertEqual(response["removed_count"], 1)
