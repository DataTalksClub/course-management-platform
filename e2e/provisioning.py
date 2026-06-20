"""Course-lifecycle provisioning and teardown via the REST API.

Design notes on teardown (important):

The CMP API is intentionally read-only for submissions, enrollments, answers
and peer reviews, and there is no course DELETE endpoint. So full teardown of
a run that has created submissions is **not possible through remote tooling
alone**:

* Homework / project objects can be DELETEd only when CLOSED and with zero
  submissions.
* Project submissions CAN be removed via the student UI (action=delete), so
  a project can be brought back to a deletable state.
* Homework submissions cannot be removed by any remote caller, so a homework
  that has been submitted to cannot be deleted. The course shell itself
  cannot be deleted either.

The teardown therefore:
  1. Deletes every deletable object (closed homeworks/projects with no
     submissions) in dependency order.
  2. Parks the residual course (rename + ``visible=false`` + ``finished``)
     so dev stays clean to anyone browsing.
  3. Reports the residual so the post-run "clean" assertion can xfail with a
     TODO pointing at #194 (needs an admin/API delete path), mirroring the
     email-verification stub.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .api_client import ApiError, CmpApiClient
from .config import NAMESPACE_PREFIX


@dataclass
class ProvisionedCourse:
    slug: str
    title: str
    homework_id: int | None = None
    homework_slug: str | None = None
    project_id: int | None = None
    project_slug: str | None = None
    question_ids: list[int] = field(default_factory=list)


def make_namespace(timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    return f"{NAMESPACE_PREFIX}{ts}"


# Question payloads exercising all three required types (FF, CB, MC) plus a
# long free-form, so the homework form renders text inputs, checkboxes and
# radios for the browser flow.
def default_questions() -> list[dict]:
    return [
        {
            "text": "What is the capital of France? (free form)",
            "question_type": "FF",
            "answer_type": "EXS",
            "correct_answer": "Paris",
            "scores_for_correct_answer": 1,
        },
        {
            "text": "Pick the even numbers (checkboxes)",
            "question_type": "CB",
            "answer_type": "ANY",
            "possible_answers": ["1", "2", "3", "4"],
            # 1-based indices of the correct options (2 and 4).
            "correct_answer": "2,4",
            "scores_for_correct_answer": 1,
        },
        {
            "text": "What is 2 + 2? (multiple choice)",
            "question_type": "MC",
            "answer_type": "INT",
            "possible_answers": ["3", "4", "5"],
            # 1-based index of the correct option ("4").
            "correct_answer": "2",
            "scores_for_correct_answer": 1,
        },
        {
            "text": "Describe what you learned (long free form)",
            "question_type": "FL",
            "answer_type": "ANY",
            "correct_answer": "",
            "scores_for_correct_answer": 0,
        },
    ]


class Provisioner:
    def __init__(self, api: CmpApiClient):
        self.api = api

    # -- create ----------------------------------------------------------
    def create_course(self, namespace: str) -> ProvisionedCourse:
        course = self.api.create_course(
            {
                "slug": namespace,
                "title": f"E2E Smoke {namespace}",
                "description": "Automated e2e smoke-test course. Safe to delete.",
                "visible": True,
            }
        )
        return ProvisionedCourse(slug=course["slug"], title=course["title"])

    def add_homework(
        self, course: ProvisionedCourse, *, due_date: str, open_now: bool = True
    ) -> None:
        hw = self.api.create_homework(
            course.slug,
            {
                "name": "E2E Homework 1",
                "slug": "hw-1",
                "due_date": due_date,
                "description": "Smoke-test homework.",
                "learning_in_public_cap": 2,
                "homework_url_field": True,
                "time_spent_lectures_field": True,
                "time_spent_homework_field": True,
                "questions": default_questions(),
            },
        )
        course.homework_id = hw["id"]
        course.homework_slug = hw["slug"]
        if open_now:
            self.api.update_homework(course.slug, hw["id"], {"state": "OP"})

    def add_project(
        self,
        course: ProvisionedCourse,
        *,
        submission_due_date: str,
        peer_review_due_date: str,
        collecting: bool = True,
    ) -> None:
        proj = self.api.create_project(
            course.slug,
            {
                "name": "E2E Project 1",
                "slug": "project-1",
                "submission_due_date": submission_due_date,
                "peer_review_due_date": peer_review_due_date,
                "description": "Smoke-test project.",
            },
        )
        course.project_id = proj["id"]
        course.project_slug = proj["slug"]
        if collecting:
            self.api.update_project(course.slug, proj["id"], {"state": "CS"})

    # -- teardown --------------------------------------------------------
    def teardown_course(self, slug: str) -> dict:
        """Best-effort teardown of a single namespaced course.

        Returns a residual report: ``{"deleted": [...], "residual": [...]}``.
        Never raises -- teardown must be robust even on partial failures.
        """
        deleted: list[str] = []
        residual: list[str] = []

        detail = self.api.get_course(slug)
        if detail is None:
            return {"deleted": deleted, "residual": residual, "course": slug}

        # Projects: close, then try delete. Submissions block deletion; the
        # caller is expected to have already removed project submissions via
        # the UI where possible.
        for proj in self.api.list_projects(slug):
            _close_and_delete(
                lambda pid: self.api.update_project(slug, pid, {"state": "CL"}),
                lambda pid: self.api.delete_project(slug, pid),
                proj,
                kind="project",
                deleted=deleted,
                residual=residual,
            )

        # Homeworks: close, then try delete.
        for hw in self.api.list_homeworks(slug):
            _close_and_delete(
                lambda hid: self.api.update_homework(slug, hid, {"state": "CL"}),
                lambda hid: self.api.delete_homework(slug, hid),
                hw,
                kind="homework",
                deleted=deleted,
                residual=residual,
            )

        # Park the course (cannot be deleted via API).
        try:
            self.api.update_course(
                slug,
                {
                    "title": f"[DELETED] {slug}",
                    "visible": False,
                    "finished": True,
                },
            )
        except ApiError:
            pass
        residual.append(f"course:{slug} (no delete endpoint; parked hidden)")

        return {"deleted": deleted, "residual": residual, "course": slug}

    def sweep_stale(self) -> list[dict]:
        """Pre-run sweep: tear down any leftover ``e2e-smoke-*`` courses."""
        reports = []
        for course in self.api.list_courses():
            slug = course.get("slug", "")
            if slug.startswith(NAMESPACE_PREFIX):
                reports.append(self.teardown_course(slug))
        return reports

    def list_active_namespaced_courses(self) -> list[str]:
        """Courses still visible under our namespace (for the clean assert)."""
        return [
            c["slug"]
            for c in self.api.list_courses()
            if c.get("slug", "").startswith(NAMESPACE_PREFIX)
            and c.get("visible", True)
        ]


def _close_and_delete(close_fn, delete_fn, obj, *, kind, deleted, residual):
    obj_id = obj.get("id")
    label = f"{kind}:{obj.get('slug', obj_id)}"
    try:
        close_fn(obj_id)
    except ApiError:
        pass
    try:
        resp = delete_fn(obj_id)
    except ApiError:
        residual.append(f"{label} (delete errored)")
        return
    if resp.status_code in (200, 404):
        deleted.append(label)
    else:
        # 400 -> blocked, typically by existing submissions.
        body = ""
        try:
            body = resp.json().get("error", "")
        except ValueError:
            body = resp.text[:120]
        residual.append(f"{label} (blocked: {body})")
