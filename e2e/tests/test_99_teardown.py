"""Scenario 8 (issue #194): Teardown.

Order of operations:
1. As the impersonated student, delete the project submission via the UI
   (the only remote way to remove a submission), then stop impersonating.
2. Via API, close + delete every deletable homework/project, and park the
   course (hidden) since there is no course DELETE endpoint.
3. Post-run assertion: no *visible* ``e2e-smoke-*`` course remains.

Known platform gap: homework submissions and enrollments cannot be deleted
by any remote caller, and courses cannot be deleted via the API. The course
is therefore hidden rather than removed, and the "fully purged" assertion is
xfailed with a TODO pointing at #194 (needs an admin/API delete path),
mirroring the email-verification stub.
"""

from __future__ import annotations

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


def test_teardown_deletes_provisioned_resources(provisioner, run_state):
    if not run_state.course:
        pytest.skip("Nothing was provisioned.")
    report = provisioner.teardown_course(run_state.course.slug)
    run_state.teardown_report = report
    print(
        f"[teardown] {report['course']}: "
        f"deleted={report['deleted']} residual={report['residual']}"
    )
    # The project (submission removed via UI) should now be deletable.
    assert any(
        item.startswith("project:") for item in report["deleted"]
    ) or run_state.course.project_id is None, (
        f"Project was not deleted in teardown: {report}"
    )


def test_no_visible_namespaced_data_remains(provisioner, run_state):
    active = provisioner.list_active_namespaced_courses()
    assert run_state.namespace not in active, (
        f"Course {run_state.namespace} is still visible after teardown: "
        f"{active}"
    )


@pytest.mark.xfail(
    reason=(
        "Homework submissions, enrollments and the course shell cannot be "
        "deleted via the API/admin, so test data cannot be fully purged "
        "remotely. TODO(#194): add an admin/API delete path for e2e cleanup."
    ),
    strict=False,
)
def test_namespaced_course_fully_purged(provisioner, run_state):
    if not run_state.course:
        pytest.skip("Nothing was provisioned.")
    # Will fail while the course still exists (parked + hidden) -> xfail.
    assert provisioner.api.get_course(run_state.namespace) is None, (
        f"Course {run_state.namespace} still exists (parked hidden). "
        f"Residual: {run_state.teardown_report.get('residual')}"
    )
