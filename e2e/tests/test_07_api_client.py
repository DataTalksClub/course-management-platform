import json
from dataclasses import dataclass

import pytest
import requests

from e2e.api_client import ApiError, ApiRequestData, CmpApiClient
from e2e.config import ConfigError


@dataclass(frozen=True)
class RequestCall:
    method: str
    url: str
    kwargs: dict


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (
            json.dumps(payload) if payload is not None else ""
        )

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
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


def client_with(responses):
    client = CmpApiClient("http://localhost:8000", "token-123")
    client.session = FakeSession(responses)
    return client


@pytest.mark.parametrize(
    ("base_url", "error"),
    [
        ("https://courses.datatalks.club", "PRODUCTION"),
        ("https://cmp.example", "non-DEV"),
    ],
)
def test_client_refuses_unsafe_host_before_opening_session(
    base_url, error, monkeypatch
):
    def unexpected_session():
        pytest.fail("Unsafe target must be rejected before opening a session")

    monkeypatch.setattr("e2e.api_client.requests.Session", unexpected_session)
    with pytest.raises(ConfigError, match=error):
        CmpApiClient(base_url, "token-123")


def test_request_retries_network_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr("e2e.api_client.time.sleep", sleeps.append)
    connection_error = requests.ConnectionError("temporary")
    success_response = FakeResponse(200, {"ok": True})
    responses = [connection_error, success_response]
    client = client_with(responses)

    request_data = ApiRequestData(method="GET", path="/api/health/")
    response = client._request(request_data)

    assert response.json() == {"ok": True}
    assert len(client.session.calls) == 2
    assert sleeps == [1.5]


def test_request_retries_transient_server_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr("e2e.api_client.time.sleep", sleeps.append)
    server_error = FakeResponse(503, {"error": "busy"})
    success_response = FakeResponse(200, {"status": "ok"})
    responses = [server_error, success_response]
    client = client_with(responses)

    request_data = ApiRequestData(method="GET", path="/api/health/")
    response = client._request(request_data)

    assert response.json() == {"status": "ok"}
    assert len(client.session.calls) == 2
    assert sleeps == [1.5]


def test_request_raises_api_error_for_unexpected_status():
    client = client_with([FakeResponse(400, {"error": "bad"})])

    with pytest.raises(ApiError) as exc:
        request_data = ApiRequestData(
            method="POST",
            path="/api/courses/",
            json_body={"slug": ""},
        )
        client._request(request_data)

    assert exc.value.status == 400
    assert exc.value.body == {"error": "bad"}
    assert "POST /api/courses/ returned 400" in str(exc.value)


def test_request_serializes_json_payload():
    client = client_with([FakeResponse(201, {"id": 1})])

    request_data = ApiRequestData(
        method="POST",
        path="/api/courses/",
        json_body={"slug": "ml-zoomcamp"},
        expected=(201,),
    )
    client._request(request_data)

    call = client.session.calls[0]
    assert call.url == "http://localhost:8000/api/courses/"
    assert call.kwargs["data"] == '{"slug": "ml-zoomcamp"}'


def test_score_homework_polls_queued_job_until_succeeded(monkeypatch):
    monkeypatch.setattr("e2e.api_client.time.sleep", lambda _: None)
    client = client_with([
        FakeResponse(202, {"status": "QUEUED", "job_id": 7}),
        FakeResponse(200, {"status": "RUNNING", "job_id": 7}),
        FakeResponse(200, {"status": "SUCCEEDED", "job_id": 7}),
    ])
    result = client.score_homework("smoke", 3)
    assert result["status"] == "SUCCEEDED"
    assert [call.method for call in client.session.calls] == ["POST", "GET", "GET"]
    assert all(call.url == "http://localhost:8000/api/courses/smoke/homeworks/3/score/" for call in client.session.calls)


def test_score_homework_reports_failed_job(monkeypatch):
    monkeypatch.setattr("e2e.api_client.time.sleep", lambda _: None)
    client = client_with([
        FakeResponse(202, {"status": "QUEUED", "job_id": 7}),
        FakeResponse(200, {"status": "FAILED", "job_id": 7, "message": "worker failed"}),
    ])
    with pytest.raises(ApiError, match="worker failed"):
        client.score_homework("smoke", 3)


def test_score_homework_times_out_without_resubmitting(monkeypatch):
    ticks = iter([0, 0, 121])
    monkeypatch.setattr("e2e.api_client.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("e2e.api_client.time.sleep", lambda _: None)
    client = client_with([
        FakeResponse(202, {"status": "QUEUED", "job_id": 7}),
        FakeResponse(200, {"status": "RUNNING", "job_id": 7}),
    ])
    with pytest.raises(ApiError, match="timed out"):
        client.score_homework("smoke", 3)
    assert [call.method for call in client.session.calls] == ["POST", "GET"]


def test_score_homework_preserves_synchronous_response():
    client = client_with([FakeResponse(200, {"status": "OK"})])
    assert client.score_homework("smoke", 3) == {"status": "OK"}
