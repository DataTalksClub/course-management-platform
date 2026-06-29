from __future__ import annotations

import json

import pytest
import requests

from e2e.api_client import ApiError, CmpApiClient


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
        self.calls.append((method, url, kwargs))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client_with(responses):
    client = CmpApiClient("https://cmp.example", "token-123")
    client.session = FakeSession(responses)
    return client


def test_request_retries_network_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr("e2e.api_client.time.sleep", sleeps.append)
    client = client_with(
        [
            requests.ConnectionError("temporary"),
            FakeResponse(200, {"ok": True}),
        ]
    )

    response = client._request("GET", "/api/health/")

    assert response.json() == {"ok": True}
    assert len(client.session.calls) == 2
    assert sleeps == [1.5]


def test_request_retries_transient_server_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr("e2e.api_client.time.sleep", sleeps.append)
    client = client_with(
        [
            FakeResponse(503, {"error": "busy"}),
            FakeResponse(200, {"status": "ok"}),
        ]
    )

    response = client._request("GET", "/api/health/")

    assert response.json() == {"status": "ok"}
    assert len(client.session.calls) == 2
    assert sleeps == [1.5]


def test_request_raises_api_error_for_unexpected_status():
    client = client_with([FakeResponse(400, {"error": "bad"})])

    with pytest.raises(ApiError) as exc:
        client._request("POST", "/api/courses/", json_body={"slug": ""})

    assert exc.value.status == 400
    assert exc.value.body == {"error": "bad"}
    assert "POST /api/courses/ returned 400" in str(exc.value)


def test_request_serializes_json_payload():
    client = client_with([FakeResponse(201, {"id": 1})])

    client._request(
        "POST",
        "/api/courses/",
        json_body={"slug": "ml-zoomcamp"},
        expected=(201,),
    )

    _method, _url, kwargs = client.session.calls[0]
    assert kwargs["data"] == '{"slug": "ml-zoomcamp"}'
