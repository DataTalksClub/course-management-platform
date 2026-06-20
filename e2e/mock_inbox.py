"""Client abstraction for the Datamailer *mock inbox* API.

The mock-inbox endpoint is a separate, in-progress sub-task of issue #194
(owned by the Datamailer repo, which this suite must NOT modify). The wire
contract is not final, so this client is deliberately small and clearly
marked. Tests that depend on it are skipped/xfailed until the real endpoint
exists and ``E2E_MOCK_INBOX_URL`` is configured.

Expected (proposed) contract -- adjust here once finalized, see #194:

    GET {mock_inbox_url}/messages?address=<email>
    Authorization: Bearer <api_key>
    -> 200 {"messages": [
            {"to": "...", "subject": "...", "html": "...", "text": "...",
             "headers": {...}, "received_at": "..."}, ...]}

``wait_for_message`` polls that endpoint until a message matching the
address (and optionally a subject substring) appears, or a timeout elapses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests


class MockInboxNotConfigured(RuntimeError):
    """Raised when the mock inbox URL has not been provided yet."""


class MockInboxTimeout(AssertionError):
    """Raised when no matching message arrives within the timeout."""


@dataclass
class InboxMessage:
    to: str
    subject: str
    html: str
    text: str
    raw: dict

    def body_contains(self, needle: str) -> bool:
        return needle in (self.html or "") or needle in (self.text or "")


class MockInboxClient:
    def __init__(
        self,
        base_url: str | None,
        api_key: str | None = None,
        *,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_messages(self, address: str) -> list[InboxMessage]:
        if not self.configured:
            raise MockInboxNotConfigured(
                "E2E_MOCK_INBOX_URL is not set; the Datamailer mock inbox "
                "endpoint is not available yet (see issue #194)."
            )
        resp = requests.get(
            f"{self.base_url}/messages",
            params={"address": address},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("messages", payload if isinstance(payload, list) else [])
        return [
            InboxMessage(
                to=item.get("to", address),
                subject=item.get("subject", ""),
                html=item.get("html", ""),
                text=item.get("text", ""),
                raw=item,
            )
            for item in items
        ]

    def wait_for_message(
        self,
        address: str,
        *,
        subject: str | None = None,
        body_contains: str | None = None,
        timeout: float = 60.0,
        poll_interval: float = 3.0,
    ) -> InboxMessage:
        """Poll until a matching message arrives or ``timeout`` elapses."""
        deadline = time.monotonic() + timeout
        last_seen: list[InboxMessage] = []
        while time.monotonic() < deadline:
            last_seen = self.list_messages(address)
            for message in last_seen:
                if subject and subject not in message.subject:
                    continue
                if body_contains and not message.body_contains(body_contains):
                    continue
                return message
            time.sleep(poll_interval)

        subjects = [m.subject for m in last_seen]
        raise MockInboxTimeout(
            f"No email to {address} matching subject={subject!r} / "
            f"body~={body_contains!r} arrived within {timeout}s. "
            f"Seen subjects: {subjects}"
        )
