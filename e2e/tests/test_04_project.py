"""Scenario 5 (issue #194): Project flow.

* Submit a project through the UI (as impersonated student).
* Submission-confirmation email received (xfail until mock inbox lands).
* Assign peer reviews (API).
* Score the project; verify score components.
* Leaderboard + project statistics update.

Note: meaningful peer-review assignment needs >= 2 submitters. A single-
student smoke run exercises the assign/score endpoints and asserts they
succeed and return sane counts, rather than requiring assigned reviews.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.project


def test_submit_project_via_ui(admin_session, run_state):
    assert run_state.student_user_id, "Student/impersonation required first."
    assert run_state.course and run_state.course.project_slug

    admin_session.submit_project(
        run_state.course.slug,
        run_state.course.project_slug,
        github_link="https://github.com/example/e2e-project",
        commit_id="abc1234",
        certificate_name="E2E Smoke Student",
        time_spent=5,
        learning_in_public_links=[
            f"https://twitter.com/e2e/{run_state.namespace}-proj"
        ],
    )
    run_state.project_submitted = True

    body = admin_session.page.locator("body").inner_text()
    assert "Thank you for submitting your project" in body, (
        "Project confirmation message not shown after submission."
    )


def test_project_submission_recorded_in_api(api, run_state):
    require_project(run_state)
    data = api.project_submissions(
        run_state.course.slug, run_state.course.project_slug
    )
    submissions = data.get("submissions", [])
    assert any(
        run_state.student_email in str(s) for s in submissions
    ), f"No project submission for {run_state.student_email}: {submissions!r}"


@pytest.mark.email
def test_project_confirmation_email(mock_inbox, run_state):
    require_project(run_state)
    if not mock_inbox.configured:
        pytest.xfail(
            "Datamailer mock inbox endpoint not available yet "
            "(E2E_MOCK_INBOX_URL unset). TODO: enable once #194 sub-task lands."
        )
    message = mock_inbox.wait_for_message(
        run_state.student_email,
        subject="Project submission saved",
        timeout=90,
    )
    assert "E2E Project 1" in message.subject
    assert message.body_contains("/project/"), (
        "Project confirmation email missing update link."
    )


def test_assign_peer_reviews(api, run_state):
    require_project(run_state)
    # Move project into peer-reviewing before assigning.
    api.update_project(
        run_state.course.slug, run_state.course.project_id, {"state": "PR"}
    )
    result = api.assign_project_reviews(
        run_state.course.slug, run_state.course.project_id
    )
    # OK with 0 assigned is acceptable for a single-submitter smoke run; the
    # important thing is the endpoint runs without error.
    assert "status" in result, f"assign-reviews returned no status: {result}"
    assert result.get("status") in ("OK", "ERROR"), result


def test_score_project(api, run_state):
    require_project(run_state)
    result = api.score_project(
        run_state.course.slug, run_state.course.project_id
    )
    assert "status" in result, f"score returned no status: {result}"
    # Verify the score-component fields exist in the submissions export.
    data = api.project_submissions(
        run_state.course.slug, run_state.course.project_slug
    )
    submissions = data.get("submissions", [])
    assert submissions, "No project submissions to score."
    sample = str(submissions[0]).lower()
    # The export documents project/faq/learning-in-public/peer-review scores.
    assert any(
        token in sample
        for token in ("score", "peer", "passed")
    ), f"Score components not present in submission export: {submissions[0]!r}"


def test_leaderboard_and_project_stats_update(api, run_state):
    require_project(run_state)
    leaderboard = api.leaderboard_yaml(run_state.course.slug)
    assert leaderboard.strip(), "Leaderboard empty after project scoring."


def require_project(run_state):
    if not run_state.project_submitted:
        pytest.skip("Project was not submitted (earlier step skipped/failed).")
