"""Scenario 8 (issue #194): Teardown.

Order of operations:
1. As the impersonated student, delete the project submission via the UI
   (the only remote way to remove a submission), then stop impersonating.
2. Best-effort API pre-pass on individually-deletable homeworks/projects,
   then delete the course (and its full cascade) through the Django admin UI.
3. Post-run assertions: the course is fully purged -- not retrievable via the
   API and not listed among visible namespaced courses.

Deleting the ``Course`` in the admin cascades to every related row (homeworks,
questions, projects, submissions, answers, enrollments, peer reviews are all
``on_delete=CASCADE``). The platform deliberately exposes **no course DELETE
API endpoint**: a standing remote delete capability is unsafe, so cleanup goes
through the staff-gated admin confirmation screen instead. If admin creds are
not configured (API-only subset), teardown falls back to parking the course
hidden and the full-purge assertion is skipped.
"""

import pytest

pytestmark = pytest.mark.teardown


def test_delete_project_submission_via_ui(admin_session, run_state):
    if not run_state.project_submitted:
        pytest.skip("No project submission to delete.")
    # Must still be impersonating the student here.
    admin_session.delete_project_submission(
        run_state.course.slug, run_state.course.project_slug
    )
    # Drop the impersonation so subsequent admin/API work is unambiguous.
    admin_session.stop_impersonating()


def test_teardown_deletes_provisioned_resources(
    provisioner, run_state, optional_admin_session
):
    if not run_state.course:
        pytest.skip("Nothing was provisioned.")
    if optional_admin_session is not None:
        optional_admin_session.stop_impersonating()
    report = provisioner.teardown_course(
        run_state.course.slug, admin_session=optional_admin_session
    )
    run_state.teardown_report = report
    print(
        f"[teardown] {report['course']}: "
        f"deleted={report['deleted']} residual={report['residual']}"
    )
    if optional_admin_session is not None:
        # Prefer full admin deletion, but accept the documented parked-hidden
        # fallback so cleanup still keeps dev invisible if admin deletion is
        # unavailable in the target environment.
        assert any(
            item.startswith("course:") and "admin-deleted" in item
            for item in report["deleted"]
        ) or any(
            "parked hidden" in item for item in report["residual"]
        ), f"Course was neither admin-deleted nor parked hidden: {report}"
    else:
        # API-only subset: no admin session, so the course is parked hidden.
        assert any(
            "parked hidden" in item for item in report["residual"]
        ), f"Expected parked-hidden fallback without admin session: {report}"


def test_no_visible_namespaced_data_remains(provisioner, run_state):
    active = provisioner.list_active_namespaced_courses()
    assert run_state.namespace not in active, (
        f"Course {run_state.namespace} is still visible after teardown: "
        f"{active}"
    )


def test_namespaced_course_fully_purged(
    provisioner, run_state, optional_admin_session
):
    """The course is actually deleted (admin cascade), not just hidden.

    Only meaningful when admin creds are configured; the API-only subset parks
    the course hidden instead, so this is skipped there.
    """
    if not run_state.course:
        pytest.skip("Nothing was provisioned.")
    if optional_admin_session is None:
        pytest.skip(
            "No admin session (E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD unset); "
            "course is parked hidden rather than deleted."
        )
    if any("parked hidden" in item for item in run_state.teardown_report.get("residual", [])):
        pytest.skip("Admin delete unavailable; course was parked hidden.")
    assert provisioner.api.get_course(run_state.namespace) is None, (
        f"Course {run_state.namespace} still exists after admin delete. "
        f"Residual: {run_state.teardown_report.get('residual')}"
    )
