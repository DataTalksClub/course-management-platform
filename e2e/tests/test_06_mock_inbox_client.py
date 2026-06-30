"""Unit-level tests for the email-verification clients (no network).

These exercise :class:`MockInboxClient` against a fake requests session, so they
run anywhere (CI, local) without the mock inbox being deployed. They lock down
the wire contract the client targets (paths, params, auth header, response
shapes, poll/timeout/clear behaviour). The *live* email assertions
(``test_03/04``) still need the mock inbox deployed to dev + creds.
"""

import json
import os

import pytest
import requests

from e2e.config import Settings, _load_dotenv, load_settings
from e2e.mock_inbox import (
    InboxClientConfig,
    InboxDisabled,
    InboxNotConfigured,
    MessageMatchCriteria,
    MessageWaitRequest,
    MockInboxClient,
    MockInboxTimeout,
    RealInboxClient,
)

pytestmark = pytest.mark.email


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    """Records requests and replays a scripted list of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        call_record = (method, url, kwargs)
        self.calls.append(call_record)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _client(responses):
    config = InboxClientConfig(
        base_url="https://datamailer.example",
        api_key="k-secret",
    )
    client = MockInboxClient(config)
    client._session = FakeSession(responses)
    client.retry_backoff = 0  # no real sleeping between retries
    return client


def _summary(**over):
    base = {
        "id": 42,
        "email": "e2e+run@mailbox.test",
        "from_email": "newsletter@example.com",
        "subject": "Homework submission saved: E2E Homework 1",
        "template_key": "homework-submission-confirmation",
        "status": "sent",
        "idempotency_key": "homework-submission:123",
        "created_at": "2026-06-20T10:00:00Z",
    }
    base.update(over)
    return base


# -- configuration ---------------------------------------------------------


def test_unconfigured_client_raises():
    config = InboxClientConfig(base_url=None, api_key=None)
    client = MockInboxClient(config)
    assert client.configured is False
    with pytest.raises(InboxNotConfigured):
        client.list_messages("e2e+x@mailbox.test")


def test_configured_requires_both_url_and_key():
    no_key = InboxClientConfig(base_url="https://x", api_key=None)
    no_url = InboxClientConfig(base_url=None, api_key="k")
    configured = InboxClientConfig(base_url="https://x", api_key="k")
    assert MockInboxClient(no_key).configured is False
    assert MockInboxClient(no_url).configured is False
    assert MockInboxClient(configured).configured is True


def test_messages_url_appends_api_path():
    config = InboxClientConfig(
        base_url="https://datamailer.example/",
        api_key="k",
    )
    client = MockInboxClient(config)
    assert client.messages_url == "https://datamailer.example/api/mock-inbox/messages"


def test_load_dotenv_sets_missing_values_only(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "E2E_EXISTING=from-file",
                "E2E_NEW='from file'",
                "E2E_QUOTED=\"quoted\"",
                "malformed",
            ]
        )
    )
    monkeypatch.setenv("E2E_EXISTING", "from-env")
    monkeypatch.delenv("E2E_NEW", raising=False)
    monkeypatch.delenv("E2E_QUOTED", raising=False)

    _load_dotenv(env_file)

    assert os.environ["E2E_EXISTING"] == "from-env"
    assert os.environ["E2E_NEW"] == "from file"
    assert os.environ["E2E_QUOTED"] == "quoted"


# -- list / auth / params --------------------------------------------------


def test_list_messages_sends_bearer_and_params():
    client = _client([FakeResponse(200, {"address": "a", "count": 1, "messages": [_summary()]})])
    messages = client.list_messages("e2e+run@mailbox.test", limit=10)

    method, url, kwargs = client._session.calls[0]
    assert method == "GET"
    assert url.endswith("/api/mock-inbox/messages")
    assert kwargs["params"] == {"address": "e2e+run@mailbox.test", "limit": 10}
    assert kwargs["headers"]["Authorization"] == "Bearer k-secret"

    assert len(messages) == 1
    msg = messages[0]
    assert msg.id == 42
    assert msg.template_key == "homework-submission-confirmation"
    assert "E2E Homework 1" in msg.subject


# -- detail + body/context matching ---------------------------------------


def test_get_message_unwraps_detail_and_loads_context():
    detail = _summary() | {
        "html_body": "<a href='/homework/hw-1'>Update your submission</a>",
        "text_body": "Update: https://x/homework/hw-1",
        "context": {"update_url": "https://x/homework/hw-1", "tags": ["a"]},
        "metadata": {"k": "v"},
    }
    client = _client([FakeResponse(200, {"message": detail})])
    msg = client.get_message(42)
    assert msg.detail_loaded
    assert msg.context["update_url"].endswith("/homework/hw-1")
    assert msg.body_contains("/homework/")  # found in context + body


def test_body_contains_checks_context_values():
    from e2e.mock_inbox import InboxMessage

    msg = InboxMessage(id=1, to="x", subject="s", context={"update_url": "https://x/homework/abc"})
    assert msg.body_contains("/homework/")
    assert not msg.body_contains("/project/")


# -- wait_for_message: matching, detail fetch, timeout ---------------------


def test_wait_for_message_matches_template_and_fetches_detail():
    list_resp = FakeResponse(200, {"messages": [_summary()]})
    detail_resp = FakeResponse(200, {"message": _summary() | {"html_body": "<p>/homework/hw-1</p>"}})
    client = _client([list_resp, detail_resp])

    request = MessageWaitRequest(
        address="e2e+run@mailbox.test",
        criteria=MessageMatchCriteria(
            template_key="homework-submission-confirmation",
            subject="Homework submission saved",
        ),
        timeout=5,
    )
    msg = client.wait_for_message(request)
    assert msg.detail_loaded
    assert msg.template_key == "homework-submission-confirmation"


def test_wait_for_message_skips_non_matching_template():
    other = _summary(template_key="welcome", subject="Welcome")
    client = _client([FakeResponse(200, {"messages": [other]})] * 50)
    request = MessageWaitRequest(
        address="e2e+run@mailbox.test",
        criteria=MessageMatchCriteria(
            template_key="homework-submission-confirmation",
        ),
        timeout=0.2,
        poll_interval=0.01,
    )
    with pytest.raises(MockInboxTimeout) as exc:
        client.wait_for_message(request)
    assert "welcome" in str(exc.value)


def test_wait_for_message_times_out_when_empty():
    client = _client([FakeResponse(200, {"messages": []})] * 50)
    request = MessageWaitRequest(
        address="e2e+run@mailbox.test",
        timeout=0.2,
        poll_interval=0.01,
    )
    with pytest.raises(MockInboxTimeout):
        client.wait_for_message(request)


# -- disabled deployment + retries -----------------------------------------


def test_disabled_deployment_raises_inbox_disabled():
    disabled = FakeResponse(404, {"error": {"code": "mock_inbox_disabled"}})
    client = _client([disabled])
    with pytest.raises(InboxDisabled):
        client.list_messages("e2e+run@mailbox.test")


def test_retries_on_transport_error_then_succeeds():
    client = _client(
        [requests.ConnectionError("boom"), FakeResponse(200, {"messages": []})]
    )
    assert client.list_messages("e2e+run@mailbox.test") == []
    assert len(client._session.calls) == 2


def test_retries_on_5xx_then_succeeds():
    client = _client([FakeResponse(503), FakeResponse(200, {"messages": []})])
    assert client.list_messages("e2e+run@mailbox.test") == []
    assert len(client._session.calls) == 2


# -- clear -----------------------------------------------------------------


def test_clear_sends_delete_with_address_and_returns_count():
    client = _client([FakeResponse(200, {"address": "a", "deleted_count": 3})])
    assert client.clear("e2e+run@mailbox.test") == 3
    method, url, kwargs = client._session.calls[0]
    assert method == "DELETE"
    assert kwargs["json"] == {"address": "e2e+run@mailbox.test"}


def test_clear_is_safe_when_unconfigured():
    config = InboxClientConfig(base_url=None, api_key=None)
    assert MockInboxClient(config).clear("x") == 0


# -- real backend (SES-inbound) --------------------------------------------


def _real_client(responses):
    config = InboxClientConfig(
        base_url="https://datamailer.example",
        api_key="k-secret",
    )
    client = RealInboxClient(config)
    client._session = FakeSession(responses)
    client.retry_backoff = 0
    return client


def _real_summary(**over):
    base = {
        "s3_key": "raw/s3oudir75a3gb1k2qlht3mianpfvr5h04ltujlo1",
        "message_id": "<abc@email.amazonses.com>",
        "from_email": "no-reply@dtcdev.click",
        "to": ["e2e+run@mailer.dtcdev.click"],
        "subject": "Homework submission saved: E2E Homework 1",
        "received_at": "2026-06-20T10:00:00Z",
    }
    base.update(over)
    return base


def test_real_inbox_configured_requires_url_and_key():
    no_key = InboxClientConfig(base_url="https://x", api_key=None)
    no_url = InboxClientConfig(base_url=None, api_key="k")
    configured = InboxClientConfig(base_url="https://x", api_key="k")
    assert RealInboxClient(no_key).configured is False
    assert RealInboxClient(no_url).configured is False
    assert RealInboxClient(configured).configured is True


def test_real_inbox_unconfigured_raises_and_clear_is_safe():
    config = InboxClientConfig(base_url=None, api_key=None)
    client = RealInboxClient(config)
    assert client.configured is False
    assert client.clear("e2e+x@mailer.dtcdev.click") == 0
    with pytest.raises(InboxNotConfigured):
        client.list_messages("e2e+x@mailer.dtcdev.click")


def test_real_inbox_messages_url_uses_inbox_path():
    config = InboxClientConfig(
        base_url="https://datamailer.example/",
        api_key="k",
    )
    client = RealInboxClient(config)
    assert client.messages_url == "https://datamailer.example/api/inbox/messages"


def test_real_list_parses_summary_without_template_key():
    client = _real_client(
        [FakeResponse(200, {"address": "a", "count": 1, "messages": [_real_summary()]})]
    )
    messages = client.list_messages("e2e+run@mailer.dtcdev.click", limit=10)

    method, url, kwargs = client._session.calls[0]
    assert method == "GET"
    assert url.endswith("/api/inbox/messages")
    assert kwargs["params"] == {"address": "e2e+run@mailer.dtcdev.click", "limit": 10}
    assert kwargs["headers"]["Authorization"] == "Bearer k-secret"

    assert len(messages) == 1
    msg = messages[0]
    # s3_key is this backend's identifier; 'to' is unwrapped from the list.
    assert msg.id == "raw/s3oudir75a3gb1k2qlht3mianpfvr5h04ltujlo1"
    assert msg.to == "e2e+run@mailer.dtcdev.click"
    assert msg.template_key == ""  # raw MIME has no template key
    assert "E2E Homework 1" in msg.subject


def test_real_get_message_for_scopes_by_address_and_loads_bodies():
    detail = _real_summary(
        text_body="Thanks -- update at https://x/homework/hw-1/",
        html_body="<p>update link</p>",
        spam_verdict="PASS",
        virus_verdict="PASS",
    )
    client = _real_client([FakeResponse(200, {"message": detail})])
    msg = client.get_message_for(
        "e2e+run@mailer.dtcdev.click",
        "raw/s3oudir75a3gb1k2qlht3mianpfvr5h04ltujlo1",
    )

    method, url, kwargs = client._session.calls[0]
    assert method == "GET"
    assert url.endswith("/api/inbox/messages/raw/s3oudir75a3gb1k2qlht3mianpfvr5h04ltujlo1")
    assert kwargs["params"] == {"address": "e2e+run@mailer.dtcdev.click"}
    assert msg.body_contains("/homework/")
    assert msg.metadata["spam_verdict"] == "PASS"


def test_real_wait_for_message_matches_subject_and_fetches_detail():
    summary = _real_summary()
    detail = _real_summary(text_body="link https://x/homework/hw-1/")
    client = _real_client(
        [
            FakeResponse(200, {"count": 1, "messages": [summary]}),  # list
            FakeResponse(200, {"message": detail}),  # address-scoped detail
        ]
    )
    request = MessageWaitRequest(
        address="e2e+run@mailer.dtcdev.click",
        criteria=MessageMatchCriteria(
            subject="Homework submission saved",
            body_contains="/homework/",
        ),
        timeout=5,
        poll_interval=0,
    )
    msg = client.wait_for_message(request)
    assert msg.body_contains("/homework/")
    # Detail fetch was address-scoped (the real backend's override).
    detail_call = client._session.calls[1]
    assert detail_call[2]["params"] == {"address": "e2e+run@mailer.dtcdev.click"}


def test_real_disabled_deployment_raises_inbox_disabled():
    client = _real_client(
        [FakeResponse(404, {"error": {"code": "real_inbox_disabled"}})]
    )
    with pytest.raises(InboxDisabled):
        client.list_messages("e2e+run@mailer.dtcdev.click")


def test_real_clear_sends_delete_with_address_and_returns_count():
    client = _real_client([FakeResponse(200, {"address": "a", "deleted_count": 3})])
    assert client.clear("e2e+run@mailer.dtcdev.click") == 3
    method, url, kwargs = client._session.calls[0]
    assert method == "DELETE"
    assert url.endswith("/api/inbox/messages")
    assert kwargs["json"] == {"address": "e2e+run@mailer.dtcdev.click"}


# -- config helper ---------------------------------------------------------


def test_mock_address_uses_tag_and_domain():
    cfg = Settings(
        base_url="https://x",
        api_token=None,
        admin_email=None,
        admin_password=None,
        student_email=None,
        student_password=None,
        mock_inbox_url=None,
        mock_inbox_api_key=None,
        mock_inbox_domain="mailbox.test",
        mock_inbox_tag="e2e",
        real_inbox_url=None,
        real_inbox_api_key=None,
        real_inbox_domain="mailer.dtcdev.click",
        real_inbox_tag="e2e",
        request_timeout=30.0,
        ui_timeout_ms=20000,
        expected_version=None,
    )
    assert cfg.mock_address("e2e-smoke-123") == "e2e+e2e-smoke-123@mailbox.test"
    # Sanitises unexpected characters in the label.
    assert cfg.mock_address("a b/c") == "e2e+a-b-c@mailbox.test"
    # The real-inbox address sits on the datamailer SES-inbound domain.
    assert cfg.real_address("e2e-smoke-123") == "e2e+e2e-smoke-123@mailer.dtcdev.click"


def test_load_settings_exposes_inbox_defaults():
    cfg = load_settings()
    assert cfg.mock_inbox_domain
    assert cfg.mock_inbox_tag
    # mock_address always yields a recognised mock address.
    assert "@" in cfg.mock_address("run")
