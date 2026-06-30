"""Scenario 7 (issue #194): Dashboards & statistics pages render.

These pages are rendered HTML, so we drive them through the browser (still
authenticated from the admin session) and assert they return 200 with the
provisioned course present, rather than 500/empty.
"""

import pytest

pytestmark = pytest.mark.dashboards


def test_course_page_renders(admin_session, run_state):
    assert run_state.course, "Course required."
    admin_session.page.goto(
        f"{admin_session.base_url}/{run_state.course.slug}/"
    )
    admin_session.page.wait_for_load_state("networkidle")
    assert admin_session.page.url.rstrip("/").endswith(run_state.course.slug)
    body = admin_session.page.locator("body").inner_text()
    assert run_state.course.title in body or "E2E Smoke" in body, (
        "Course page did not render the provisioned course title."
    )


def test_dashboard_renders(admin_session, run_state):
    assert run_state.course, "Course required."
    resp = admin_session.page.goto(
        f"{admin_session.base_url}/{run_state.course.slug}/dashboard"
    )
    admin_session.page.wait_for_load_state("networkidle")
    assert resp is None or resp.status < 500, (
        f"Dashboard returned server error: "
        f"{resp.status if resp else 'unknown'}"
    )
    body = admin_session.page.locator("body").inner_text()
    assert body.strip(), "Dashboard rendered empty."


def test_leaderboard_renders(admin_session, run_state):
    assert run_state.course, "Course required."
    resp = admin_session.page.goto(
        f"{admin_session.base_url}/{run_state.course.slug}/leaderboard"
    )
    admin_session.page.wait_for_load_state("networkidle")
    assert resp is None or resp.status < 500, (
        f"Leaderboard returned server error: "
        f"{resp.status if resp else 'unknown'}"
    )
    body = admin_session.page.locator("body").inner_text()
    assert body.strip(), "Leaderboard rendered empty."
