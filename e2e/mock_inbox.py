"""Email-verification clients for the e2e smoke suite.

Two backends sit behind one interface (:class:`InboxBackend`) so the email
tests don't care which one they run against:

* :class:`RealInboxClient` -- the **default** backend. Datamailer really sends
  via SES to a recognised real-inbox address
  (``e2e+<tag>@mailer.dtcdev.click``), SES inbound writes the raw MIME to S3,
  and this client lists / fetches / clears those received messages over HTTP.

* :class:`MockInboxClient` -- the fast, deterministic opt-in backend. It talks
  to the Datamailer *mock inbox* API. Transactional sends to a recognised mock
  address (``e2e+<tag>@mailbox.test``) are captured as ``TransactionalMessage``
  rows instead of being delivered for real.

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
    """Raised when the deployment has the selected inbox turned off (404)."""


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
        strings = []
        for value in (self.context or {}).values():
            strings.extend(context_value_strings(value))
        return strings


def context_value_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        strings = []
        for item in value:
            strings.append(str(item))
        return strings
    return []


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

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        backend_name: str,
        disabled_message: str,
        **kwargs,
    ) -> requests.Response:
        """Issue a request with retries on transient transport/5xx errors."""
        self._require_configured()
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                self._handle_request_exception(exc, attempt)
                continue

            self._raise_if_disabled(resp, disabled_message)
            if self._should_retry_response(resp, attempt):
                self._sleep_before_retry(attempt)
                continue
            return resp

        raise RuntimeError(f"{backend_name} request failed")

    def _handle_request_exception(
        self,
        exc: requests.RequestException,
        attempt: int,
    ) -> None:
        if attempt == self.max_retries:
            raise exc
        self._sleep_before_retry(attempt)

    def _raise_if_disabled(
        self,
        resp: requests.Response,
        disabled_message: str,
    ) -> None:
        if resp.status_code == 404 and self._looks_disabled(resp):
            raise InboxDisabled(disabled_message)

    def _should_retry_response(
        self,
        resp: requests.Response,
        attempt: int,
    ) -> bool:
        return resp.status_code >= 500 and attempt < self.max_retries

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(self.retry_backoff * attempt)

    def _fetch_detail(self, address: str, message: "InboxMessage") -> "InboxMessage":
        """Load a message's full detail (bodies/context) during polling.

        Default keys only off the message id. Backends whose detail route also
        needs the recipient address (the real inbox) override this.
        """
        return self.get_message(message.id)

    def _summary_matches(
        self,
        message: InboxMessage,
        *,
        template_key: str | None,
        subject: str | None,
    ) -> bool:
        if template_key and message.template_key != template_key:
            return False
        if subject and subject not in message.subject:
            return False
        return True

    def _message_with_detail(
        self,
        address: str,
        message: InboxMessage,
        load_detail: bool,
    ) -> InboxMessage:
        if load_detail and not message.detail_loaded:
            return self._fetch_detail(address, message)
        return message

    def _message_matches_body(
        self,
        address: str,
        message: InboxMessage,
        *,
        body_contains: str | None,
        load_detail: bool,
    ) -> InboxMessage | None:
        if not body_contains:
            return message

        candidate = self._message_with_detail(address, message, load_detail)
        if candidate.body_contains(body_contains):
            return candidate if load_detail else message
        return None

    def _matched_message(
        self,
        address: str,
        messages: list[InboxMessage],
        *,
        template_key: str | None,
        subject: str | None,
        body_contains: str | None,
        load_detail: bool,
    ) -> InboxMessage | None:
        for message in messages:
            matched = self._matched_candidate(
                address,
                message,
                template_key=template_key,
                subject=subject,
                body_contains=body_contains,
                load_detail=load_detail,
            )
            if matched is not None:
                return matched

        return None

    def _matched_candidate(
        self,
        address: str,
        message: InboxMessage,
        *,
        template_key: str | None,
        subject: str | None,
        body_contains: str | None,
        load_detail: bool,
    ) -> InboxMessage | None:
        if not self._summary_matches(
            message,
            template_key=template_key,
            subject=subject,
        ):
            return None

        matched = self._message_matches_body(
            address,
            message,
            body_contains=body_contains,
            load_detail=load_detail,
        )
        if matched is None:
            return None
        return self._matched_with_optional_detail(
            address,
            message,
            matched,
            body_contains=body_contains,
            load_detail=load_detail,
        )

    def _matched_with_optional_detail(
        self,
        address: str,
        message: InboxMessage,
        matched: InboxMessage,
        *,
        body_contains: str | None,
        load_detail: bool,
    ) -> InboxMessage:
        if load_detail and not body_contains and message.id is not None:
            return self._fetch_detail(address, message)
        return matched

    def _timeout_error(
        self,
        address: str,
        *,
        template_key: str | None,
        subject: str | None,
        body_contains: str | None,
        timeout: float,
        last_seen: list[InboxMessage],
        last_error: Exception | None,
    ) -> MockInboxTimeout:
        seen = []
        for message in last_seen:
            seen.append((message.template_key, message.subject))
        hint = f" Last error: {last_error!r}." if last_error else ""
        return MockInboxTimeout(
            f"[{self.name}] No email to {address} matching "
            f"template_key={template_key!r} / subject={subject!r} / "
            f"body~={body_contains!r} within {timeout}s. Seen: {seen}.{hint}"
        )

    def _poll_for_message_match(
        self,
        address: str,
        *,
        template_key: str | None,
        subject: str | None,
        body_contains: str | None,
        load_detail: bool,
        poll_interval: float,
    ) -> tuple[InboxMessage | None, list[InboxMessage] | None, Exception | None]:
        try:
            messages = self.list_messages(address)
        except (requests.RequestException, InboxDisabled) as exc:
            # Transient network hiccup or a not-yet-ready deployment: keep
            # polling until the deadline rather than failing immediately.
            time.sleep(poll_interval)
            return None, None, exc

        matched = self._matched_message(
            address,
            messages,
            template_key=template_key,
            subject=subject,
            body_contains=body_contains,
            load_detail=load_detail,
        )
        if matched is None:
            time.sleep(poll_interval)
        return matched, messages, None

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
        """Poll until a matching message arrives or ``timeout`` elapses."""
        deadline = time.monotonic() + timeout
        last_seen: list[InboxMessage] = []
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            matched, seen, error = self._poll_for_message_match(
                address,
                template_key=template_key,
                subject=subject,
                body_contains=body_contains,
                load_detail=load_detail,
                poll_interval=poll_interval,
            )
            if matched is not None:
                return matched
            last_seen = seen if seen is not None else last_seen
            last_error = error if error is not None else last_error

        raise self._timeout_error(
            address,
            template_key=template_key,
            subject=subject,
            body_contains=body_contains,
            timeout=timeout,
            last_seen=last_seen,
            last_error=last_error,
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
        return self._request_with_retries(
            method,
            url,
            backend_name="mock inbox",
            disabled_message=(
                "Mock inbox is disabled on this deployment "
                "(MOCK_INBOX_ENABLED is off). 404 mock_inbox_disabled."
            ),
            **kwargs,
        )

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
        messages = []
        for item in items:
            messages.append(self._summary_to_message(item, address))
        return messages

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


REAL_INBOX_PATH = "/api/inbox/messages"


class RealInboxClient(InboxBackend):
    """HTTP client for the Datamailer real-inbox (SES-inbound) read API.

    Unlike the mock backend, this proves an email was *actually sent via SES and
    received in a real mailbox*: Datamailer really sends to a real-inbox address
    (``e2e+<tag>@mailer.dtcdev.click``), an SES receipt rule writes the raw MIME
    to S3, and this API parses it back out. Same client Bearer auth as the mock
    inbox; the base URL is the Datamailer service root.

    Wire contract (datamailer ``docs/api.md`` "Real Inbox"):

        GET    {base}/api/inbox/messages?address=<addr>&limit=25
            -> 200 {"address","count","messages":[{s3_key,message_id,from_email,
                    to:[...],subject,received_at}, ...]}  (newest first)
        GET    {base}/api/inbox/messages/{s3_key}?address=<addr>
            -> 200 {"message":{...summary..., text_body, html_body,
                    spam_verdict, virus_verdict}}
        DELETE {base}/api/inbox/messages   body {"address":"<addr>"}
            -> 200 {"address","deleted_count"}

    Differences from the mock backend the caller must know about:

    * Messages are parsed from raw MIME, so there is **no ``template_key``** --
      match on ``subject`` / ``body_contains`` instead.
    * Capture is scoped only to the recipient address (not to a Datamailer
      client), so isolate runs with a unique ``+<tag>``.
    * Delivery to S3 is eventually consistent (~5-15s); poll until ``count > 0``.

    When ``REAL_INBOX_ENABLED`` is off the routes return
    ``404 {"error": {"code": "real_inbox_disabled"}}``.
    """

    name = "real"

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
        return f"{self.base_url}{REAL_INBOX_PATH}"

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _require_configured(self) -> None:
        if not self.configured:
            raise InboxNotConfigured(
                "E2E_REAL_INBOX_URL / E2E_REAL_INBOX_API_KEY (falling back to "
                "DATAMAILER_URL / DATAMAILER_API_KEY) are not set; the "
                "Datamailer real inbox is not reachable."
            )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        return self._request_with_retries(
            method,
            url,
            backend_name="real inbox",
            disabled_message=(
                "Real inbox is disabled on this deployment "
                "(REAL_INBOX_ENABLED is off). 404 real_inbox_disabled."
            ),
            **kwargs,
        )

    @staticmethod
    def _looks_disabled(resp: requests.Response) -> bool:
        try:
            body = resp.json()
        except ValueError:
            return False
        return (body.get("error") or {}).get("code") == "real_inbox_disabled"

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        # requests urlencodes the params, turning the address '+' into '%2B'
        # (not a space), which is exactly what the API requires.
        resp = self._request(
            "GET", self.messages_url, params={"address": address, "limit": limit}
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("messages", []) if isinstance(payload, dict) else []
        messages = []
        for item in items:
            messages.append(self._summary_to_message(item, address))
        return messages

    def _fetch_detail(self, address: str, message: InboxMessage) -> InboxMessage:
        # The real-inbox detail route needs the address as a scope, so the
        # default (id-only) hook is overridden here.
        return self.get_message_for(address, message.id)

    def get_message_for(self, address: str, s3_key) -> InboxMessage:
        resp = self._request(
            "GET",
            f"{self.messages_url}/{s3_key}",
            params={"address": address},
        )
        resp.raise_for_status()
        payload = resp.json()
        item = payload.get("message", payload) if isinstance(payload, dict) else {}
        return self._detail_to_message(item, address)

    def clear(self, address: str | None = None) -> int:
        """Delete the captured S3 objects for ``address`` (teardown)."""
        body: dict = {}
        if address:
            body["address"] = address
        try:
            resp = self._request("DELETE", self.messages_url, json=body)
        except (InboxNotConfigured, InboxDisabled):
            return 0
        if resp.status_code >= 400:
            return 0
        try:
            return int(resp.json().get("deleted_count", 0))
        except (ValueError, AttributeError, TypeError):
            return 0

    @staticmethod
    def _summary_to_message(item: dict, address: str) -> InboxMessage:
        to = item.get("to") or []
        return InboxMessage(
            # The s3_key is this backend's stable per-message identifier.
            id=item.get("s3_key"),
            to=(to[0] if isinstance(to, list) and to else address),
            subject=item.get("subject", ""),
            # Real MIME has no template_key -- callers match on subject/body.
            template_key="",
            from_email=item.get("from_email", ""),
            created_at=item.get("received_at", ""),
            raw=item,
        )

    @classmethod
    def _detail_to_message(cls, item: dict, address: str) -> InboxMessage:
        message = cls._summary_to_message(item, address)
        message.html_body = item.get("html_body", "") or ""
        message.text_body = item.get("text_body", "") or ""
        # No render context in received MIME; expose the SES verdicts instead.
        message.metadata = {
            "spam_verdict": item.get("spam_verdict", ""),
            "virus_verdict": item.get("virus_verdict", ""),
            "message_id": item.get("message_id", ""),
        }
        return message
