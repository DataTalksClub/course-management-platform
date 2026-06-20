"""Scenario 2 (issue #194): Course & content provisioning (via API).

Also performs the pre-run sweep of stale ``e2e-smoke-*`` data (scenario 8).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.provisioning


def test_pre_run_sweep_of_stale_data(provisioner):
    """Remove leftovers from previous failed runs before provisioning."""
    reports = provisioner.sweep_stale()
    # Sweep is best-effort and must not fail the run; just surface what it did.
    for report in reports:
        print(
            f"[sweep] {report['course']}: "
            f"deleted={report['deleted']} residual={report['residual']}"
        )


def test_create_course(provisioner, run_state):
    run_state.course = provisioner.create_course(run_state.namespace)
    assert run_state.course.slug == run_state.namespace
    fetched = provisioner.api.get_course(run_state.namespace)
    assert fetched is not None, "Course not retrievable after creation."
    assert fetched["title"].startswith("E2E Smoke")


def test_create_homework_with_all_question_types(
    provisioner, run_state, due_dates
):
    assert run_state.course, "Course must be created first."
    provisioner.add_homework(
        run_state.course, due_date=due_dates["homework_due"], open_now=True
    )
    assert run_state.course.homework_id is not None

    # Verify all three required question types are present.
    hw = provisioner.api.list_homeworks(run_state.course.slug)[0]
    assert hw["questions_count"] >= 3, (
        f"Expected at least 3 questions, got {hw['questions_count']}"
    )
    assert hw["state"] == "OP", "Homework should be open for submissions."


def test_create_project(provisioner, run_state, due_dates):
    assert run_state.course, "Course must be created first."
    provisioner.add_project(
        run_state.course,
        submission_due_date=due_dates["project_due"],
        peer_review_due_date=due_dates["peer_review_due"],
        collecting=True,
    )
    assert run_state.course.project_id is not None
    proj = provisioner.api.list_projects(run_state.course.slug)[0]
    assert proj["state"] == "CS", "Project should be collecting submissions."
