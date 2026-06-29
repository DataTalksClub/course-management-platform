"""Course-lifecycle provisioning and teardown.

Provisioning and the deletable-object pre-pass go through the REST API (fast,
token-auth). The **course itself is deleted through the Django admin UI**
(driven by Playwright), not via a REST endpoint.

Design notes on teardown (important):

The CMP API is intentionally read-only for submissions, enrollments, answers
and peer reviews, and there is deliberately **no course DELETE API endpoint**:
a standing remote delete capability could let any API client/agent wipe too
much data. Admin-panel deletion is instead gated behind an interactive staff
login plus the admin's own confirmation screen, which is the safer path.

Deleting a ``Course`` through the admin cascades to ALL of its data --
Homework, Question, Project, Submission, Answer, ProjectSubmission,
Enrollment, PeerReview are all ``on_delete=CASCADE`` from Course/Project -- so
one admin delete of the course fully cleans a run.

The teardown therefore:
  1. (Best-effort, optional) deletes individual deletable objects via the API
     in dependency order -- harmless even though the admin delete supersedes
     it; keeps the report informative.
  2. Deletes the course through the admin UI (``admin_session``), which
     cascades away every remaining row.
  3. Falls back to *parking* the course (rename + ``visible=false`` +
     ``finished``) only if the admin delete is unavailable or fails, so dev
     still stays clean to anyone browsing, and reports the residual.

When the admin delete succeeds there is no residual and the course is fully
purged.
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


@dataclass(frozen=True)
class AdminDeleteResultData:
    slug: str
    admin_session: object
    detail: dict
    deleted: list[str]
    residual: list[str]


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
    def _delete_project_prepass(
        self,
        slug: str,
        deleted: list[str],
        residual: list[str],
    ) -> None:
        projects = self.api.list_projects(slug)
        for proj in projects:
            _close_and_delete(
                lambda pid: self.api.update_project(slug, pid, {"state": "CL"}),
                lambda pid: self.api.delete_project(slug, pid),
                proj,
                kind="project",
                deleted=deleted,
                residual=residual,
            )

    def _delete_homework_prepass(
        self,
        slug: str,
        deleted: list[str],
        residual: list[str],
    ) -> None:
        homeworks = self.api.list_homeworks(slug)
        for hw in homeworks:
            _close_and_delete(
                lambda hid: self.api.update_homework(slug, hid, {"state": "CL"}),
                lambda hid: self.api.delete_homework(slug, hid),
                hw,
                kind="homework",
                deleted=deleted,
                residual=residual,
            )

    def _delete_child_objects(
        self,
        slug: str,
        deleted: list[str],
        residual: list[str],
    ) -> None:
        self._delete_project_prepass(slug, deleted, residual)
        self._delete_homework_prepass(slug, deleted, residual)

    def _admin_delete_course(
        self,
        slug: str,
        detail: dict,
        admin_session,
    ) -> bool:
        course_pk = detail.get("id") if isinstance(detail, dict) else None

        try:
            purged = admin_session.delete_course_via_admin(slug, course_pk=course_pk)
        except Exception:
            purged = False

        return bool(purged and self.api.get_course(slug) is None)

    def _record_admin_delete_result(
        self,
        data: AdminDeleteResultData,
    ) -> bool:
        if data.admin_session is None:
            data.residual.append(
                f"course:{data.slug} (no admin session; parked hidden)"
            )
            return False

        if self._admin_delete_course(
            data.slug,
            data.detail,
            data.admin_session,
        ):
            data.deleted.append(
                f"course:{data.slug} (admin-deleted, cascaded)"
            )
            return True

        data.residual.append(
            f"course:{data.slug} (admin delete failed; parked hidden)"
        )
        return False

    def _park_course_hidden(self, slug: str) -> None:
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

    def _teardown_report(
        self,
        slug: str,
        deleted: list[str],
        residual: list[str],
    ) -> dict:
        return {"deleted": deleted, "residual": residual, "course": slug}

    def teardown_course(self, slug: str, admin_session=None) -> dict:
        """Best-effort teardown of a single namespaced course.

        The course (and its full cascade) is deleted through the Django admin
        UI when an authenticated ``admin_session`` is supplied. If no session
        is given, or the admin delete fails, the course is *parked hidden* as
        a fallback so dev stays clean and the residual is reported.

        Returns a residual report:
        ``{"deleted": [...], "residual": [...], "course": slug}``.
        Never raises -- teardown must be robust even on partial failures.
        """
        deleted: list[str] = []
        residual: list[str] = []

        detail = self.api.get_course(slug)
        if detail is None:
            return self._teardown_report(slug, deleted, residual)

        # Best-effort API pre-pass on individually-deletable objects. This is
        # informative for the report; the admin delete below supersedes it by
        # cascading everything away regardless.
        self._delete_child_objects(slug, deleted, residual)

        # Primary path: delete the course (and its cascade) via the admin UI.
        admin_delete_data = AdminDeleteResultData(
            slug=slug,
            admin_session=admin_session,
            detail=detail,
            deleted=deleted,
            residual=residual,
        )
        if self._record_admin_delete_result(admin_delete_data):
            return self._teardown_report(slug, deleted, residual)

        # Fallback: park the course hidden so dev stays clean.
        self._park_course_hidden(slug)

        return self._teardown_report(slug, deleted, residual)

    def sweep_stale(self, admin_session=None) -> list[dict]:
        """Pre-run sweep: tear down any leftover ``e2e-smoke-*`` courses.

        Uses admin-UI deletion (cascade) when an ``admin_session`` is given,
        otherwise falls back to parking each stale course hidden.
        """
        reports = []
        courses = self.api.list_courses()
        for course in courses:
            slug = course.get("slug", "")
            if slug.startswith(NAMESPACE_PREFIX):
                report = self.teardown_course(
                    slug,
                    admin_session=admin_session,
                )
                reports.append(report)
        return reports

    def list_active_namespaced_courses(self) -> list[str]:
        """Courses still visible under our namespace (for the clean assert)."""
        slugs = []
        courses = self.api.list_courses()
        for course in courses:
            if not course.get("slug", "").startswith(NAMESPACE_PREFIX):
                continue
            if not course.get("visible", True):
                continue
            slugs.append(course["slug"])
        return slugs


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
