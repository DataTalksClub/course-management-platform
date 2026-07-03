"""Thin REST client for the CMP API used for fast provisioning, scoring,
assertions and teardown.

Only the endpoints the suite actually needs are wrapped. Each call raises
``ApiError`` with a clear, scenario-friendly message on unexpected status
codes so failures point straight at the broken step.

Auth: ``Authorization: Token <token>`` (staff token). See endpoints.md.
"""

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        self.status = status
        self.body = body
        super().__init__(message)


class SendAuditTimeout(AssertionError):
    """Raised when no matching Datamailer send audit appears in time."""


@dataclass(frozen=True)
class ApiRequestData:
    method: str
    path: str
    json_body: Any = None
    expected: tuple[int, ...] = (200, 201)
    retries: int = 2


@dataclass(frozen=True)
class ApiResponseValidationData:
    request: ApiRequestData
    response: requests.Response


@dataclass(frozen=True)
class ApiNetworkErrorData:
    request: ApiRequestData
    exc: requests.RequestException


class CmpApiClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # -- low level -------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, data: ApiRequestData) -> requests.Response:
        url = self._url(data.path)
        last_exc: Exception | None = None
        for attempt in range(data.retries + 1):
            try:
                resp = self._send_request(data.method, url, data.json_body)
            except requests.RequestException as exc:  # network blip
                last_exc = exc
                if attempt < data.retries:
                    self._sleep_before_retry(attempt)
                    continue
                error_data = ApiNetworkErrorData(request=data, exc=exc)
                self._raise_network_error(error_data)

            if self._should_retry_response(resp, attempt, data.retries):
                self._sleep_before_retry(attempt)
                continue

            validation_data = ApiResponseValidationData(
                request=data,
                response=resp,
            )
            self._validate_response(validation_data)
            return resp

        # Unreachable, but keeps type-checkers happy.
        raise ApiError(f"{data.method} {data.path} failed: {last_exc}")

    def _send_request(
        self,
        method: str,
        url: str,
        json_body: Any,
    ) -> requests.Response:
        data = None
        if json_body is not None:
            data = json.dumps(json_body)
        return self.session.request(
            method,
            url,
            data=data,
            timeout=self.timeout,
        )

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(1.5 * (attempt + 1))

    def _should_retry_response(
        self,
        resp: requests.Response,
        attempt: int,
        retries: int,
    ) -> bool:
        return resp.status_code >= 500 and attempt < retries

    def _validate_response(self, data: ApiResponseValidationData) -> None:
        if data.response.status_code in data.request.expected:
            return

        response_body = _safe_json(data.response)
        raise ApiError(
            f"{data.request.method} {data.request.path} "
            f"returned {data.response.status_code} "
            f"(expected {data.request.expected}): {data.response.text[:500]}",
            status=data.response.status_code,
            body=response_body,
        )

    def _raise_network_error(self, data: ApiNetworkErrorData) -> None:
        raise ApiError(
            f"{data.request.method} {data.request.path} failed after "
            f"{data.request.retries + 1} attempts: {data.exc}"
        ) from data.exc

    # -- health ----------------------------------------------------------
    def health(self) -> dict:
        request_data = ApiRequestData(
            method="GET",
            path="/api/health/",
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    # -- courses ---------------------------------------------------------
    def list_courses(self) -> list[dict]:
        request_data = ApiRequestData(
            method="GET",
            path="/api/courses/",
            expected=(200,),
        )
        resp = self._request(request_data)
        body = resp.json()
        courses = body.get("courses", [])
        return courses

    def create_course(self, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path="/api/courses/",
            json_body=payload,
            expected=(201,),
        )
        resp = self._request(request_data)
        return resp.json()

    def get_course(self, slug: str) -> dict | None:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{slug}/",
            expected=(200, 404),
        )
        resp = self._request(request_data)
        if resp.status_code != 200:
            return None
        body = resp.json()
        return body

    def update_course(self, slug: str, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="PATCH",
            path=f"/api/courses/{slug}/",
            json_body=payload,
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    # -- homeworks -------------------------------------------------------
    def create_homework(self, course_slug: str, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path=f"/api/courses/{course_slug}/homeworks/",
            json_body=payload,
            expected=(201,),
        )
        resp = self._request(request_data)
        body = resp.json()
        created = body.get("created", [])
        if not created:
            raise ApiError(
                f"Homework creation returned no created records: {body}"
            )
        return created[0]

    def list_homeworks(self, course_slug: str) -> list[dict]:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{course_slug}/homeworks/",
            expected=(200,),
        )
        resp = self._request(request_data)
        body = resp.json()
        homeworks = body.get("homeworks", [])
        return homeworks

    def update_homework(self, course_slug: str, hw_id: int, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="PATCH",
            path=f"/api/courses/{course_slug}/homeworks/{hw_id}/",
            json_body=payload,
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    def delete_homework(self, course_slug: str, hw_id: int) -> requests.Response:
        # 200 = deleted, 400 = blocked (has submissions / not closed).
        request_data = ApiRequestData(
            method="DELETE",
            path=f"/api/courses/{course_slug}/homeworks/{hw_id}/",
            expected=(200, 400, 404),
        )
        return self._request(request_data)

    def score_homework(self, course_slug: str, hw_id: int) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path=f"/api/courses/{course_slug}/homeworks/{hw_id}/score/",
            expected=(200, 400),
        )
        resp = self._request(request_data)
        return resp.json()

    def homework_submissions(self, course_slug: str, hw_slug: str) -> dict:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{course_slug}/homeworks/{hw_slug}/submissions",
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    # -- projects --------------------------------------------------------
    def create_project(self, course_slug: str, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path=f"/api/courses/{course_slug}/projects/",
            json_body=payload,
            expected=(201,),
        )
        resp = self._request(request_data)
        body = resp.json()
        created = body.get("created", [])
        if not created:
            raise ApiError(
                f"Project creation returned no created records: {body}"
            )
        return created[0]

    def list_projects(self, course_slug: str) -> list[dict]:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{course_slug}/projects/",
            expected=(200,),
        )
        resp = self._request(request_data)
        body = resp.json()
        projects = body.get("projects", [])
        return projects

    def update_project(self, course_slug: str, proj_id: int, payload: dict) -> dict:
        request_data = ApiRequestData(
            method="PATCH",
            path=f"/api/courses/{course_slug}/projects/{proj_id}/",
            json_body=payload,
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    def delete_project(self, course_slug: str, proj_id: int) -> requests.Response:
        request_data = ApiRequestData(
            method="DELETE",
            path=f"/api/courses/{course_slug}/projects/{proj_id}/",
            expected=(200, 400, 404),
        )
        return self._request(request_data)

    def assign_project_reviews(self, course_slug: str, proj_id: int) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path=f"/api/courses/{course_slug}/projects/{proj_id}/assign-reviews/",
            expected=(200, 400),
        )
        resp = self._request(request_data)
        return resp.json()

    def score_project(self, course_slug: str, proj_id: int) -> dict:
        request_data = ApiRequestData(
            method="POST",
            path=f"/api/courses/{course_slug}/projects/{proj_id}/score/",
            expected=(200, 400),
        )
        resp = self._request(request_data)
        return resp.json()

    def project_submissions(self, course_slug: str, proj_slug: str) -> dict:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{course_slug}/projects/{proj_slug}/submissions",
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.json()

    # -- leaderboard -----------------------------------------------------
    def leaderboard_yaml(self, course_slug: str) -> str:
        request_data = ApiRequestData(
            method="GET",
            path=f"/api/courses/{course_slug}/leaderboard.yaml",
            expected=(200,),
        )
        resp = self._request(request_data)
        return resp.text

    # -- datamailer send audits -----------------------------------------
    def datamailer_send_audits(
        self,
        *,
        email: str | None = None,
        template_key: str | None = None,
        idempotency_key: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """List CMP's own Datamailer send-audit rows (newest first).

        Mirrors the production email path: every send goes outbox -> dispatch
        -> ``/api/transactional/send`` -> ``DatamailerSendAudit``. With
        ``DATAMAILER_TRANSACTIONAL_DRY_RUN=1`` on the target, the audit's
        ``response_payload`` carries the rendered subject/bodies without
        anything being delivered.
        """
        params: list[tuple[str, str]] = []
        if email:
            params.append(("email", email))
        if template_key:
            params.append(("template_key", template_key))
        if idempotency_key:
            params.append(("idempotency_key", idempotency_key))
        if limit is not None:
            params.append(("limit", str(limit)))
        path = "/api/datamailer/send-audits"
        if params:
            path = f"{path}?{urlencode(params)}"
        request_data = ApiRequestData(
            method="GET",
            path=path,
            expected=(200,),
        )
        resp = self._request(request_data)
        body = resp.json()
        return body.get("audits", [])

    def wait_for_send_audit(
        self,
        email: str,
        template_key: str,
        *,
        body_contains: str | None = None,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
    ) -> dict:
        """Poll the send-audit endpoint until a matching audit appears.

        The outbox dispatch is normally synchronous, so the audit is usually
        present on the first poll; the short retry only smooths over dispatch
        latency. Raises :class:`SendAuditTimeout` if nothing matches in time.
        """
        deadline = time.monotonic() + timeout
        seen: list[dict] = []
        while True:
            audits = self.datamailer_send_audits(
                email=email,
                template_key=template_key,
            )
            match = _first_matching_audit(audits, body_contains)
            if match is not None:
                return match
            seen = audits
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_interval)

        raise SendAuditTimeout(
            f"No Datamailer send audit for {email!r} with "
            f"template_key={template_key!r} / body~={body_contains!r} within "
            f"{timeout}s. Seen: {[a.get('idempotency_key') for a in seen]!r}. "
            "Is Datamailer configured on the target with "
            "DATAMAILER_TRANSACTIONAL_DRY_RUN=1?"
        )


def send_audit_body_contains(audit: dict, needle: str) -> bool:
    """True if ``needle`` appears in the audit's rendered bodies or context.

    Checks ``rendered.html_body`` / ``rendered.text_body`` and, when present,
    the stringified values of ``response_payload.context`` (confirmation links
    live in the render context as well as the rendered HTML).
    """
    for haystack in _audit_haystacks(audit):
        if needle in haystack:
            return True
    return False


def _audit_haystacks(audit: dict) -> list[str]:
    rendered = audit.get("rendered") or {}
    haystacks = [
        rendered.get("html_body") or "",
        rendered.get("text_body") or "",
    ]
    payload = audit.get("response_payload") or {}
    context = payload.get("context") or {}
    if isinstance(context, dict):
        for value in context.values():
            haystacks.append(str(value))
    return haystacks


def _first_matching_audit(
    audits: list[dict],
    body_contains: str | None,
) -> dict | None:
    for audit in audits:
        if body_contains and not send_audit_body_contains(audit, body_contains):
            continue
        return audit
    return None


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
