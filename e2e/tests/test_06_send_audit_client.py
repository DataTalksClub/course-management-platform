"""Unit-level tests for the Datamailer send-audit reader (no network).

These exercise :class:`CmpApiClient`'s ``datamailer_send_audits`` /
``wait_for_send_audit`` against a fake requests session, so they run anywhere
(CI, local) without a live target. They lock down the wire contract the client
targets (path, query params, auth header, response shape, poll/timeout, and the
rendered-body matching used by the email tests). The *live* email assertions
(``test_03/04``) still need a deployed dev target running with
``RELAY_TRANSACTIONAL_DRY_RUN=1``.
"""

import json
from dataclasses import dataclass

import pytest

from e2e.api_client import (
    CmpApiClient,
    SendAuditTimeout,
    send_audit_body_contains,
)
from e2e.config import Settings, _load_dotenv, load_settings

pytestmark = pytest.mark.email


@dataclass(frozen=True)
class RequestCall:
    method: str
    url: str
    kwargs: dict


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Records requests and replays a scripted list of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        call_record = RequestCall(method=method, url=url, kwargs=kwargs)
        self.calls.append(call_record)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _client(responses):
    client = CmpApiClient("https://cmp.example", "token-123")
    client.session = FakeSession(responses)
    return client


def _audit(**over):
    base = {
        "send_type": "transactional",
        "status": "succeeded",
        "template_key": "homework-submission-confirmation",
        "idempotency_key": "homework-submission:123",
        "occurred_at": "2026-06-20T10:00:00Z",
        "would_deliver": True,
        "rendered": {
            "subject": "Homework submission saved: E2E Homework 1",
            "html_body": "<a href='/homework/hw-1'>Update your submission</a>",
            "text_body": "Update: https://x/homework/hw-1",
        },
        "message": {
            "email": "e2e-smoke-1@example.com",
            "template_key": "homework-submission-confirmation",
        },
        "response_payload": {"context": {}},
    }
    base.update(over)
    return base


# -- list: path, params, auth ---------------------------------------------


def test_send_audits_sends_token_and_query_params():
    client = _client([FakeResponse(200, {"audits": [_audit()], "count": 1})])
    audits = client.datamailer_send_audits(
        email="e2e-smoke-1@example.com",
        template_key="homework-submission-confirmation",
        limit=10,
    )

    call = client.session.calls[0]
    assert call.method == "GET"
    assert call.url.startswith(
        "https://cmp.example/api/datamailer/send-audits?"
    )
    assert "email=e2e-smoke-1%40example.com" in call.url
    assert "template_key=homework-submission-confirmation" in call.url
    assert "limit=10" in call.url

    assert len(audits) == 1
    assert audits[0]["template_key"] == "homework-submission-confirmation"


def test_client_sets_token_auth_header_on_session():
    client = CmpApiClient("https://cmp.example", "token-123")
    assert client.session.headers["Authorization"] == "Token token-123"


def test_send_audits_without_filters_hits_bare_path():
    client = _client([FakeResponse(200, {"audits": [], "count": 0})])
    assert client.datamailer_send_audits() == []
    call = client.session.calls[0]
    assert call.url == "https://cmp.example/api/datamailer/send-audits"


# -- body matching ---------------------------------------------------------


def test_send_audit_body_contains_checks_rendered_bodies():
    audit = _audit()
    assert send_audit_body_contains(audit, "/homework/")
    assert not send_audit_body_contains(audit, "/project/")


def test_send_audit_body_contains_checks_response_payload_context():
    audit = _audit(
        rendered={"html_body": "", "text_body": ""},
        response_payload={"context": {"update_url": "https://x/homework/abc"}},
    )
    assert send_audit_body_contains(audit, "/homework/")


# -- wait_for_send_audit ---------------------------------------------------


def test_wait_for_send_audit_returns_first_match():
    client = _client([FakeResponse(200, {"audits": [_audit()], "count": 1})])
    audit = client.wait_for_send_audit(
        "e2e-smoke-1@example.com",
        "homework-submission-confirmation",
        body_contains="/homework/",
        timeout=5,
        poll_interval=0,
    )
    assert audit["idempotency_key"] == "homework-submission:123"


def test_wait_for_send_audit_polls_until_match(monkeypatch):
    sleeps = []
    monkeypatch.setattr("e2e.api_client.time.sleep", sleeps.append)
    empty = FakeResponse(200, {"audits": [], "count": 0})
    ready = FakeResponse(200, {"audits": [_audit()], "count": 1})
    client = _client([empty, ready])

    audit = client.wait_for_send_audit(
        "e2e-smoke-1@example.com",
        "homework-submission-confirmation",
        body_contains="/homework/",
        timeout=5,
        poll_interval=1,
    )
    assert audit["template_key"] == "homework-submission-confirmation"
    assert len(client.session.calls) == 2
    assert sleeps == [1]


def test_wait_for_send_audit_times_out_when_body_never_matches():
    # Real (tiny) poll sleeps bound the iteration count under the deadline.
    wrong_body = _audit(
        rendered={"html_body": "no link", "text_body": "no link"},
        response_payload={"context": {}},
    )
    responses = [FakeResponse(200, {"audits": [wrong_body], "count": 1})] * 500
    client = _client(responses)

    with pytest.raises(SendAuditTimeout):
        client.wait_for_send_audit(
            "e2e-smoke-1@example.com",
            "homework-submission-confirmation",
            body_contains="/homework/",
            timeout=0.2,
            poll_interval=0.02,
        )


def test_wait_for_send_audit_times_out_when_empty():
    responses = [FakeResponse(200, {"audits": [], "count": 0})] * 500
    client = _client(responses)
    with pytest.raises(SendAuditTimeout):
        client.wait_for_send_audit(
            "e2e-smoke-1@example.com",
            "homework-submission-confirmation",
            timeout=0.2,
            poll_interval=0.02,
        )


# -- config helpers --------------------------------------------------------


def test_student_address_is_namespaced_and_sanitised():
    cfg = load_settings()
    assert cfg.student_address("e2e-smoke-123") == "e2e-smoke-123@example.com"
    # Sanitises unexpected characters in the label.
    assert cfg.student_address("a b/c") == "a-b-c@example.com"


def test_load_settings_returns_settings():
    cfg = load_settings()
    assert isinstance(cfg, Settings)
    assert cfg.base_url


def test_load_dotenv_sets_missing_values_only(tmp_path, monkeypatch):
    import os

    env_file = tmp_path / ".env"
    env_lines = [
        "# comment",
        "E2E_EXISTING=from-file",
        "E2E_NEW='from file'",
        "E2E_QUOTED=\"quoted\"",
        "malformed",
    ]
    env_file.write_text("\n".join(env_lines))
    monkeypatch.setenv("E2E_EXISTING", "from-env")
    monkeypatch.delenv("E2E_NEW", raising=False)
    monkeypatch.delenv("E2E_QUOTED", raising=False)

    _load_dotenv(env_file)

    assert os.environ["E2E_EXISTING"] == "from-env"
    assert os.environ["E2E_NEW"] == "from file"
    assert os.environ["E2E_QUOTED"] == "quoted"


# -- prod hard-gate (t1283u) -----------------------------------------------


def test_assert_safe_e2e_base_url_allows_dev():
    from e2e.config import assert_safe_e2e_base_url

    assert (
        assert_safe_e2e_base_url("https://dev.courses.datatalks.club")
        == "https://dev.courses.datatalks.club"
    )
    assert (
        assert_safe_e2e_base_url("https://dev.courses.datatalks.club/")
        == "https://dev.courses.datatalks.club"
    )


def test_assert_safe_e2e_base_url_allows_localhost():
    from e2e.config import assert_safe_e2e_base_url

    assert assert_safe_e2e_base_url("http://localhost:8000") == "http://localhost:8000"
    assert assert_safe_e2e_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_assert_safe_e2e_base_url_refuses_prod():
    from e2e.config import ConfigError, assert_safe_e2e_base_url

    for url in (
        "https://courses.datatalks.club",
        "https://courses.datatalks.club/",
        "https://www.courses.datatalks.club",
        "http://courses.datatalks.club/admin/",
    ):
        with pytest.raises(ConfigError, match="PRODUCTION"):
            assert_safe_e2e_base_url(url)


def test_assert_safe_e2e_base_url_refuses_unknown_remote():
    from e2e.config import ConfigError, assert_safe_e2e_base_url

    with pytest.raises(ConfigError, match="non-DEV"):
        assert_safe_e2e_base_url("https://staging.courses.datatalks.club")


def test_load_settings_refuses_prod_base_url(monkeypatch):
    from e2e.config import ConfigError, load_settings

    monkeypatch.setenv("E2E_BASE_URL", "https://courses.datatalks.club")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    with pytest.raises(ConfigError, match="PRODUCTION"):
        load_settings()


def test_api_token_ignores_prod_named_env(monkeypatch):
    from e2e.config import _api_token_from_env

    monkeypatch.delenv("E2E_API_TOKEN", raising=False)
    monkeypatch.delenv("DEV_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PROD_AUTH_TOKEN", "should-not-be-used")
    monkeypatch.setenv("PRODUCTION_API_TOKEN", "also-ignored")
    assert _api_token_from_env() is None


def test_create_course_refuses_prod_base_url(monkeypatch):
    from e2e.api_client import CmpApiClient
    from e2e.config import ConfigError

    with pytest.raises(ConfigError, match="PRODUCTION"):
        CmpApiClient("https://courses.datatalks.club", "token")
