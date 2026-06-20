"""Thin REST client for the CMP API used for fast provisioning, scoring,
assertions and teardown.

Only the endpoints the suite actually needs are wrapped. Each call raises
``ApiError`` with a clear, scenario-friendly message on unexpected status
codes so failures point straight at the broken step.

Auth: ``Authorization: Token <token>`` (staff token). See endpoints.md.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        self.status = status
        self.body = body
        super().__init__(message)


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

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        expected: tuple[int, ...] = (200, 201),
        retries: int = 2,
    ) -> requests.Response:
        url = self._url(path)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    data=json.dumps(json_body) if json_body is not None else None,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # network blip
                last_exc = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise ApiError(
                    f"{method} {path} failed after {retries + 1} attempts: {exc}"
                ) from exc

            # Retry transient 5xx once or twice.
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code not in expected:
                raise ApiError(
                    f"{method} {path} returned {resp.status_code} "
                    f"(expected {expected}): {resp.text[:500]}",
                    status=resp.status_code,
                    body=_safe_json(resp),
                )
            return resp

        # Unreachable, but keeps type-checkers happy.
        raise ApiError(f"{method} {path} failed: {last_exc}")

    # -- health ----------------------------------------------------------
    def health(self) -> dict:
        resp = self._request("GET", "/api/health/", expected=(200,))
        return resp.json()

    # -- courses ---------------------------------------------------------
    def list_courses(self) -> list[dict]:
        resp = self._request("GET", "/api/courses/", expected=(200,))
        return resp.json().get("courses", [])

    def create_course(self, payload: dict) -> dict:
        resp = self._request(
            "POST", "/api/courses/", json_body=payload, expected=(201,)
        )
        return resp.json()

    def get_course(self, slug: str) -> dict | None:
        resp = self._request(
            "GET", f"/api/courses/{slug}/", expected=(200, 404)
        )
        return resp.json() if resp.status_code == 200 else None

    def update_course(self, slug: str, payload: dict) -> dict:
        resp = self._request(
            "PATCH", f"/api/courses/{slug}/", json_body=payload, expected=(200,)
        )
        return resp.json()

    # -- homeworks -------------------------------------------------------
    def create_homework(self, course_slug: str, payload: dict) -> dict:
        resp = self._request(
            "POST",
            f"/api/courses/{course_slug}/homeworks/",
            json_body=payload,
            expected=(201,),
        )
        body = resp.json()
        created = body.get("created", [])
        if not created:
            raise ApiError(
                f"Homework creation returned no created records: {body}"
            )
        return created[0]

    def list_homeworks(self, course_slug: str) -> list[dict]:
        resp = self._request(
            "GET", f"/api/courses/{course_slug}/homeworks/", expected=(200,)
        )
        return resp.json().get("homeworks", [])

    def update_homework(self, course_slug: str, hw_id: int, payload: dict) -> dict:
        resp = self._request(
            "PATCH",
            f"/api/courses/{course_slug}/homeworks/{hw_id}/",
            json_body=payload,
            expected=(200,),
        )
        return resp.json()

    def delete_homework(self, course_slug: str, hw_id: int) -> requests.Response:
        # 200 = deleted, 400 = blocked (has submissions / not closed).
        return self._request(
            "DELETE",
            f"/api/courses/{course_slug}/homeworks/{hw_id}/",
            expected=(200, 400, 404),
        )

    def score_homework(self, course_slug: str, hw_id: int) -> dict:
        resp = self._request(
            "POST",
            f"/api/courses/{course_slug}/homeworks/{hw_id}/score/",
            expected=(200, 400),
        )
        return resp.json()

    def homework_submissions(self, course_slug: str, hw_slug: str) -> dict:
        resp = self._request(
            "GET",
            f"/api/courses/{course_slug}/homeworks/{hw_slug}/submissions",
            expected=(200,),
        )
        return resp.json()

    # -- projects --------------------------------------------------------
    def create_project(self, course_slug: str, payload: dict) -> dict:
        resp = self._request(
            "POST",
            f"/api/courses/{course_slug}/projects/",
            json_body=payload,
            expected=(201,),
        )
        body = resp.json()
        created = body.get("created", [])
        if not created:
            raise ApiError(
                f"Project creation returned no created records: {body}"
            )
        return created[0]

    def list_projects(self, course_slug: str) -> list[dict]:
        resp = self._request(
            "GET", f"/api/courses/{course_slug}/projects/", expected=(200,)
        )
        return resp.json().get("projects", [])

    def update_project(self, course_slug: str, proj_id: int, payload: dict) -> dict:
        resp = self._request(
            "PATCH",
            f"/api/courses/{course_slug}/projects/{proj_id}/",
            json_body=payload,
            expected=(200,),
        )
        return resp.json()

    def delete_project(self, course_slug: str, proj_id: int) -> requests.Response:
        return self._request(
            "DELETE",
            f"/api/courses/{course_slug}/projects/{proj_id}/",
            expected=(200, 400, 404),
        )

    def assign_project_reviews(self, course_slug: str, proj_id: int) -> dict:
        resp = self._request(
            "POST",
            f"/api/courses/{course_slug}/projects/{proj_id}/assign-reviews/",
            expected=(200, 400),
        )
        return resp.json()

    def score_project(self, course_slug: str, proj_id: int) -> dict:
        resp = self._request(
            "POST",
            f"/api/courses/{course_slug}/projects/{proj_id}/score/",
            expected=(200, 400),
        )
        return resp.json()

    def project_submissions(self, course_slug: str, proj_slug: str) -> dict:
        resp = self._request(
            "GET",
            f"/api/courses/{course_slug}/projects/{proj_slug}/submissions",
            expected=(200,),
        )
        return resp.json()

    # -- leaderboard -----------------------------------------------------
    def leaderboard_yaml(self, course_slug: str) -> str:
        resp = self._request(
            "GET",
            f"/api/courses/{course_slug}/leaderboard.yaml",
            expected=(200,),
        )
        return resp.text


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
