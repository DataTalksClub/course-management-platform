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
        has_body = bool(self.html_body or self.text_body)
        has_context = bool(self.context)
        return has_body or has_context

    def body_contains(self, needle: str) -> bool:
        """True if ``needle`` appears in the rendered bodies or the context.

        Confirmation links live in ``context`` (e.g. ``update_url``) as well as
        the rendered HTML, so we check both.
        """
        haystacks = [self.html_body or "", self.text_body or ""]
        context_strings = self._context_strings()
        haystacks.extend(context_strings)
        for haystack in haystacks:
            if needle in haystack:
                return True
        return False

    def _context_strings(self) -> list[str]:
        strings = []
        context_values = (self.context or {}).values()
        for value in context_values:
            value_strings = context_value_strings(value)
            strings.extend(value_strings)
        return strings


@dataclass(frozen=True)
class MessageMatchCriteria:
    template_key: str | None = None
    subject: str | None = None
    body_contains: str | None = None
    load_detail: bool = True


@dataclass(frozen=True)
class MessageWaitRequest:
    address: str
    criteria: MessageMatchCriteria = field(default_factory=MessageMatchCriteria)
    timeout: float = 90.0
    poll_interval: float = 3.0


@dataclass
class MessageWaitState:
    last_seen: list[InboxMessage] = field(default_factory=list)
    last_error: Exception | None = None


@dataclass(frozen=True)
class MessageWaitData:
    request: MessageWaitRequest
    state: MessageWaitState


@dataclass(frozen=True)
class MessageBatchMatchData:
    address: str
    messages: list[InboxMessage]
    criteria: MessageMatchCriteria


@dataclass(frozen=True)
class MessageCandidateMatchData:
    address: str
    message: InboxMessage
    criteria: MessageMatchCriteria


@dataclass
class MessagePollResult:
    matched: InboxMessage | None = None
    seen: list[InboxMessage] | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class InboxRetryConfig:
    timeout: float = 15.0
    max_retries: int = 3
    retry_backoff: float = 0.5


@dataclass(frozen=True)
class InboxClientConfig:
    base_url: str | None
    api_key: str | None = None
    retry: InboxRetryConfig = field(default_factory=InboxRetryConfig)


@dataclass(frozen=True)
class InboxRequestData:
    method: str
    url: str
    backend_name: str
    disabled_message: str
    request_kwargs: dict = field(default_factory=dict)


def context_value_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        strings = []
        for item in value:
            string = str(item)
            strings.append(string)
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

    def _set_http_client_config(self, config: InboxClientConfig) -> None:
        if config.base_url:
            base_url = config.base_url.rstrip("/")
        else:
            base_url = None
        self.base_url = base_url
        self.api_key = config.api_key
        self.timeout = config.retry.timeout
        self.max_retries = config.retry.max_retries
        self.retry_backoff = config.retry.retry_backoff
        self._session = requests.Session()

    def _request_with_retries(self, data: InboxRequestData) -> requests.Response:
        """Issue a request with retries on transient transport/5xx errors."""
        self._require_configured()
        request_kwargs = data.request_kwargs.copy()
        headers = self._headers()
        request_kwargs.setdefault("headers", headers)
        request_kwargs.setdefault("timeout", self.timeout)
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.request(
                    data.method,
                    data.url,
                    **request_kwargs,
                )
            except requests.RequestException as exc:
                self._handle_request_exception(exc, attempt)
                continue

            self._raise_if_disabled(resp, data.disabled_message)
            if self._should_retry_response(resp, attempt):
                self._sleep_before_retry(attempt)
                continue
            return resp

        raise RuntimeError(f"{data.backend_name} request failed")

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
        criteria: MessageMatchCriteria,
    ) -> bool:
        if criteria.template_key and message.template_key != criteria.template_key:
            return False
        if criteria.subject and criteria.subject not in message.subject:
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

    def _matched_message(self, data: MessageBatchMatchData) -> InboxMessage | None:
        for message in data.messages:
            candidate_data = MessageCandidateMatchData(
                address=data.address,
                message=message,
                criteria=data.criteria,
            )
            matched = self._matched_candidate(candidate_data)
            if matched is not None:
                return matched

        return None

    def _matched_candidate(
        self,
        data: MessageCandidateMatchData,
    ) -> InboxMessage | None:
        if not self._summary_matches(data.message, data.criteria):
            return None

        if not data.criteria.body_contains:
            return self._matched_without_body_filter(data)

        candidate = self._message_with_detail(
            data.address,
            data.message,
            data.criteria.load_detail,
        )
        if not candidate.body_contains(data.criteria.body_contains):
            return None
        if data.criteria.load_detail:
            return candidate
        return data.message

    def _matched_without_body_filter(
        self,
        data: MessageCandidateMatchData,
    ) -> InboxMessage:
        if data.criteria.load_detail and data.message.id is not None:
            return self._fetch_detail(data.address, data.message)
        return data.message

    def _timeout_error(self, data: MessageWaitData) -> MockInboxTimeout:
        seen = []
        for message in data.state.last_seen:
            seen_record = (message.template_key, message.subject)
            seen.append(seen_record)
        hint = ""
        if data.state.last_error:
            hint = f" Last error: {data.state.last_error!r}."
        return MockInboxTimeout(
            f"[{self.name}] No email to {data.request.address} matching "
            f"template_key={data.request.criteria.template_key!r} / "
            f"subject={data.request.criteria.subject!r} / "
            f"body~={data.request.criteria.body_contains!r} within "
            f"{data.request.timeout}s. Seen: {seen}.{hint}"
        )

    def _poll_for_message_match(
        self,
        data: MessageWaitData,
    ) -> MessagePollResult:
        try:
            messages = self.list_messages(data.request.address)
        except (requests.RequestException, InboxDisabled) as exc:
            # Transient network hiccup or a not-yet-ready deployment: keep
            # polling until the deadline rather than failing immediately.
            time.sleep(data.request.poll_interval)
            return MessagePollResult(error=exc)

        batch_data = MessageBatchMatchData(
            address=data.request.address,
            messages=messages,
            criteria=data.request.criteria,
        )
        matched = self._matched_message(batch_data)
        if matched is None:
            time.sleep(data.request.poll_interval)
        return MessagePollResult(matched=matched, seen=messages)

    def wait_for_message(self, request: MessageWaitRequest) -> InboxMessage:
        """Poll until a matching message arrives or ``timeout`` elapses."""
        state = MessageWaitState()
        wait_data = MessageWaitData(
            request=request,
            state=state,
        )
        return self._wait_for_message_or_timeout(wait_data)

    def _wait_for_message_or_timeout(self, data: MessageWaitData) -> InboxMessage:
        deadline = time.monotonic() + data.request.timeout
        while time.monotonic() < deadline:
            result = self._poll_for_message_match(data)
            if result.matched is not None:
                return result.matched
            if result.seen is not None:
                data.state.last_seen = result.seen
            if result.error is not None:
                data.state.last_error = result.error

        raise self._timeout_error(data)


class MockInboxClient(InboxBackend):
    """HTTP client for the Datamailer mock-inbox API (default backend)."""

    name = "mock"

    def __init__(self, config: InboxClientConfig):
        self._set_http_client_config(config)

    @property
    def configured(self) -> bool:
        has_base_url = bool(self.base_url)
        has_api_key = bool(self.api_key)
        return has_base_url and has_api_key

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
        request_data = InboxRequestData(
            method=method,
            url=url,
            backend_name="mock inbox",
            disabled_message=(
                "Mock inbox is disabled on this deployment "
                "(MOCK_INBOX_ENABLED is off). 404 mock_inbox_disabled."
            ),
            request_kwargs=kwargs,
        )
        return self._request_with_retries(request_data)

    @staticmethod
    def _looks_disabled(resp: requests.Response) -> bool:
        try:
            body = resp.json()
        except ValueError:
            return False
        error = body.get("error") or {}
        error_code = error.get("code")
        return error_code == "mock_inbox_disabled"

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        resp = self._request(
            "GET", self.messages_url, params={"address": address, "limit": limit}
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):
            items = payload.get("messages", [])
        else:
            items = []
        messages = []
        for item in items:
            message = self._summary_to_message(item, address)
            messages.append(message)
        return messages

    def get_message(self, message_id) -> InboxMessage:
        resp = self._request("GET", f"{self.messages_url}/{message_id}")
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):
            item = payload.get("message", payload)
        else:
            item = {}
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
            response_body = resp.json()
            deleted_count = response_body.get("deleted_count", 0)
            return int(deleted_count)
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
        fallback_address = item.get("email", "")
        message = cls._summary_to_message(item, fallback_address)
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

    def __init__(self, config: InboxClientConfig):
        self._set_http_client_config(config)

    @property
    def configured(self) -> bool:
        has_base_url = bool(self.base_url)
        has_api_key = bool(self.api_key)
        return has_base_url and has_api_key

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
        request_data = InboxRequestData(
            method=method,
            url=url,
            backend_name="real inbox",
            disabled_message=(
                "Real inbox is disabled on this deployment "
                "(REAL_INBOX_ENABLED is off). 404 real_inbox_disabled."
            ),
            request_kwargs=kwargs,
        )
        return self._request_with_retries(request_data)

    @staticmethod
    def _looks_disabled(resp: requests.Response) -> bool:
        try:
            body = resp.json()
        except ValueError:
            return False
        error = body.get("error") or {}
        error_code = error.get("code")
        return error_code == "real_inbox_disabled"

    def list_messages(self, address: str, *, limit: int = 25) -> list[InboxMessage]:
        # requests urlencodes the params, turning the address '+' into '%2B'
        # (not a space), which is exactly what the API requires.
        resp = self._request(
            "GET", self.messages_url, params={"address": address, "limit": limit}
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):
            items = payload.get("messages", [])
        else:
            items = []
        messages = []
        for item in items:
            message = self._summary_to_message(item, address)
            messages.append(message)
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
        if isinstance(payload, dict):
            item = payload.get("message", payload)
        else:
            item = {}
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
            response_body = resp.json()
            deleted_count = response_body.get("deleted_count", 0)
            return int(deleted_count)
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
