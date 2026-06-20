"""Email-verification clients for the e2e smoke suite.

Two backends sit behind one interface (:class:`InboxBackend`) so the email
tests don't care which one they run against:

* :class:`MockInboxClient` -- the **default**, fast, deterministic backend. It
  talks to the Datamailer *mock inbox* API (issue #194, owned by the
  ``datamailer/`` repo). Transactional sends to a recognised "mock address"
  (``e2e+<tag>@mailbox.test`` or ``e2e+<tag>@<dev-domain>``) are captured as
  ``TransactionalMessage`` rows instead of being delivered for real, and this
  client lists / fetches / clears them over HTTP.

* :class:`RealInboxClient` -- a **stub** for a real SES inbound round-trip
  (issue #194 sub-task ``issue-194-ses-inbound``). Its read contract is not
  final yet, so this client is intentionally not implemented; one or two tests
  opt into it and skip/xfail until ``E2E_REAL_INBOX_*`` config is provided.

Mock-inbox wire contract (datamailer ``issue-194-mock-inbox``), base URL is the
Datamailer service root (``E2E_MOCK_INBOX_URL`` / ``DATAMAILER_URL``), auth is
``Authorization: Bearer <client api key>``:

    GET    {base}/api/mock-inbox/messages?address=<addr>&limit=25
        -> 200 {"address","count","messages":[{id,email,from_email,subject,
                template_key,status,idempotency_key,created_at}, ...]}  (newest first)
    GET    {base}/api/mock-inbox/messages/{id}
        -> 200 {"message":{...summary..., html_body, text_body, context, metadata}}
    DELETE {base}/api/mock-inbox/messages   body {"address":"<addr>"} (or empty = clear all)
        -> 200 {"address","deleted_count"}

When the mock inbox is disabled on the deployment, every route returns
``404 {"error": {"code": "mock_inbox_disabled"}}``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

MOCK_INBOX_PATH = "/api/mock-inbox/messages"


class InboxNotConfigured(RuntimeError):
    """Raised when a backend's URL/key has not been provided yet."""


class InboxDisabled(RuntimeError):
    """Raised when the deployment has the mock inbox turned off (404)."""


class MockInboxTimeout(AssertionError):
    """Raised when no matching message arrives within the timeout."""


# Backwards-compatible alias (kept so older imports keep working).
MockInboxNotConfigured = InboxNotConfigured


@dataclass
class InboxMessage:
    """A captured email, normalised across backends.

    ``raw`` holds the backend's original summary dict; ``html_body`` /
    ``text_body`` / ``context`` are only populated once a detail fetch happens
    (the list endpoint returns summaries only).
    """

    id: int | str | None
    to: str
    subject: str
    template_key: str = ""
    status: str = ""
    from_email: str = ""
    idempotency_key: str = ""
    created_at: str = ""
    html_body: str = ""
    text_body: str = ""
    context: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def detail_loaded(self) -> bool:
        return bool(self.html_body or self.text_body or self.context)

    def body_contains(self, needle: str) -> bool:
        """True if ``needle`` appears in the rendered bodies or the context.

        Confirmation links live in ``context`` (e.g. ``update_url``) as well as
        the rendered HTML, so we check both.
        """
        haystacks = [self.html_body or "", self.text_body or ""]
        haystacks.extend(self._context_strings())
        return any(needle in h for h in haystacks)

    def _context_strings(self) -> list[str]:
        out: list[str] = []
        for value in (self.context or {}).values():
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, (list, tuple)):
                out.extend(str(v) for v in value)
        return out


class InboxBackend:
    """Common interface implemented by both backends."""

    name = "inbox"

    @property
    def configured(self) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        raise NotImplementedError

    def get_message(self, message_id) -> InboxMessage:
        raise NotImplementedError

    def clear(self, address: str | None = None) -> int:
        raise NotImplementedError

    def wait_for_message(
        self,
        address: str,
        *,
        template_key: str | None = None,
        subject: str | None = None,
        body_contains: str | None = None,
        timeout: float = 90.0,
        poll_interval: float = 3.0,
        load_detail: bool = True,
    ) -> InboxMessage:
        """Poll until a matching message arrives or ``timeout`` elapses.

        Matching is by ``template_key`` (exact), ``subject`` (substring) and/or
        ``body_contains`` (substring across bodies + context). When
        ``load_detail`` is set, the matched message's full detail (bodies +
        context) is fetched before returning so callers can assert on links.
        """
        deadline = time.monotonic() + timeout
        last_seen: list[InboxMessage] = []
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                last_seen = self.list_messages(address)
            except (requests.RequestException, InboxDisabled) as exc:
                # Transient network hiccup or a not-yet-ready deployment: keep
                # polling until the deadline rather than failing immediately.
                last_error = exc
                time.sleep(poll_interval)
                continue

            for message in last_seen:
                if template_key and message.template_key != template_key:
                    continue
                if subject and subject not in message.subject:
                    continue
                if body_contains:
                    candidate = message
                    if load_detail and not message.detail_loaded:
                        candidate = self.get_message(message.id)
                    if not candidate.body_contains(body_contains):
                        continue
                    if load_detail:
                        return candidate
                    return message
                if load_detail and message.id is not None:
                    return self.get_message(message.id)
                return message

            time.sleep(poll_interval)

        seen = [(m.template_key, m.subject) for m in last_seen]
        hint = f" Last error: {last_error!r}." if last_error else ""
        raise MockInboxTimeout(
            f"[{self.name}] No email to {address} matching "
            f"template_key={template_key!r} / subject={subject!r} / "
            f"body~={body_contains!r} within {timeout}s. Seen: {seen}.{hint}"
        )


class MockInboxClient(InboxBackend):
    """HTTP client for the Datamailer mock-inbox API (default backend)."""

    name = "mock"

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None = None,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._session = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @property
    def messages_url(self) -> str:
        return f"{self.base_url}{MOCK_INBOX_PATH}"

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _require_configured(self) -> None:
        if not self.configured:
            raise InboxNotConfigured(
                "E2E_MOCK_INBOX_URL / E2E_MOCK_INBOX_API_KEY (falling back to "
                "DATAMAILER_URL / DATAMAILER_API_KEY) are not set; the "
                "Datamailer mock inbox is not reachable (see issue #194)."
            )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Issue a request with retries on transient transport/5xx errors."""
        self._require_configured()
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    raise
                time.sleep(self.retry_backoff * attempt)
                continue

            if resp.status_code == 404 and self._looks_disabled(resp):
                raise InboxDisabled(
                    "Mock inbox is disabled on this deployment "
                    "(MOCK_INBOX_ENABLED is off). 404 mock_inbox_disabled."
                )
            if resp.status_code >= 500 and attempt < self.max_retries:
                last_exc = requests.HTTPError(f"{resp.status_code} from mock inbox")
                time.sleep(self.retry_backoff * attempt)
                continue
            return resp

        # Unreachable, but keeps type-checkers happy.
        raise last_exc or RuntimeError("mock inbox request failed")

    @staticmethod
    def _looks_disabled(resp: requests.Response) -> bool:
        try:
            body = resp.json()
        except ValueError:
            return False
        return (body.get("error") or {}).get("code") == "mock_inbox_disabled"

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        resp = self._request(
            "GET", self.messages_url, params={"address": address, "limit": limit}
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("messages", []) if isinstance(payload, dict) else []
        return [self._summary_to_message(item, address) for item in items]

    def get_message(self, message_id) -> InboxMessage:
        resp = self._request("GET", f"{self.messages_url}/{message_id}")
        resp.raise_for_status()
        payload = resp.json()
        item = payload.get("message", payload) if isinstance(payload, dict) else {}
        return self._detail_to_message(item)

    def clear(self, address: str | None = None) -> int:
        """Delete captured messages for ``address`` (or all when ``None``)."""
        body: dict = {}
        if address:
            body["address"] = address
        try:
            resp = self._request("DELETE", self.messages_url, json=body)
        except (InboxNotConfigured, InboxDisabled):
            # Teardown must never explode; nothing to clear if unreachable.
            return 0
        if resp.status_code >= 400:
            return 0
        try:
            return int(resp.json().get("deleted_count", 0))
        except (ValueError, AttributeError, TypeError):
            return 0

    @staticmethod
    def _summary_to_message(item: dict, address: str) -> InboxMessage:
        return InboxMessage(
            id=item.get("id"),
            to=item.get("email", address),
            subject=item.get("subject", ""),
            template_key=item.get("template_key", ""),
            status=item.get("status", ""),
            from_email=item.get("from_email", ""),
            idempotency_key=item.get("idempotency_key", ""),
            created_at=item.get("created_at", ""),
            raw=item,
        )

    @classmethod
    def _detail_to_message(cls, item: dict) -> InboxMessage:
        message = cls._summary_to_message(item, item.get("email", ""))
        message.html_body = item.get("html_body", "") or ""
        message.text_body = item.get("text_body", "") or ""
        message.context = item.get("context") or {}
        message.metadata = item.get("metadata") or {}
        return message


class RealInboxClient(InboxBackend):
    """Stub for the real SES-inbound round-trip backend.

    TODO(issue #194 / branch ``issue-194-ses-inbound``): implement against the
    real inbound-capture read API once its contract is finalised. Until then
    this client reports itself unconfigured so the one or two tests that select
    it skip/xfail cleanly instead of blocking the suite. The constructor mirrors
    :class:`MockInboxClient` so the swap is a one-liner once the contract lands.
    """

    name = "real"

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
        # Intentionally always False until E2E_REAL_INBOX_* + the read contract
        # exist. Flip this to ``bool(self.base_url and self.api_key)`` and fill
        # in the methods below once issue-194-ses-inbound ships.
        return False

    def _not_ready(self):
        raise InboxNotConfigured(
            "Real SES-inbound inbox backend is not implemented yet "
            "(issue #194, branch issue-194-ses-inbound). Set E2E_REAL_INBOX_URL "
            "/ E2E_REAL_INBOX_API_KEY and implement RealInboxClient once the "
            "read contract is finalised."
        )

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        self._not_ready()

    def get_message(self, message_id) -> InboxMessage:
        self._not_ready()

    def clear(self, address: str | None = None) -> int:
        # Safe no-op so teardown never fails on the unconfigured real backend.
        return 0
