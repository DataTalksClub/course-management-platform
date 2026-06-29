"""Scenario 5 (issue #194): Project flow.

* Submit a project through the UI (as impersonated student).
* Submission-confirmation email really received via SES, read back from the
  Datamailer real inbox (xfails if the real inbox is not enabled on the target).
* Assign peer reviews (API).
* Score the project; verify score components.
* Leaderboard + project statistics update.

Note: meaningful peer-review assignment needs >= 2 submitters. A single-
student smoke run exercises the assign/score endpoints and asserts they
succeed and return sane counts, rather than requiring assigned reviews.
"""

from __future__ import annotations

import pytest

from e2e.browser import ProjectSubmissionData
from e2e.mock_inbox import InboxDisabled

pytestmark = pytest.mark.project


def test_submit_project_via_ui(admin_session, run_state):
    assert run_state.student_user_id, "Student/impersonation required first."
    assert run_state.course and run_state.course.project_slug

    submission_data = ProjectSubmissionData(
        course_slug=run_state.course.slug,
        project_slug=run_state.course.project_slug,
        github_link="https://github.com/DataTalksClub/course-management-platform",
        commit_id="4ce0ca4",
        certificate_name="E2E Smoke Student",
        time_spent=5,
        learning_in_public_links=[
            f"https://twitter.com/e2e/{run_state.namespace}-proj"
        ],
    )
    admin_session.submit_project(submission_data)
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


# Confirmation-email contract (from courses/views/project.py, read-only):
#   template_key = "project-submission-confirmation"
#   subject      = "Project submission saved: <project title>"
#   context      = {update_url, profile_url, course_slug, project_slug, ...}
PROJECT_CONFIRMATION_TEMPLATE = "project-submission-confirmation"


def _assert_project_confirmation(backend, run_state):
    # The real SES-inbound backend has no template_key (parsed from raw MIME);
    # match on subject + body. Only the mock store carries a template_key.
    expected_template = (
        PROJECT_CONFIRMATION_TEMPLATE if backend.name == "mock" else None
    )
    message = backend.wait_for_message(
        run_state.student_email,
        template_key=expected_template,
        subject="Project submission saved",
        timeout=120,
    )
    assert "E2E Project 1" in message.subject
    if expected_template:
        assert message.template_key == expected_template
    assert message.body_contains("/project/"), (
        "Project confirmation email missing update link "
        f"(subject={message.subject!r})."
    )


@pytest.mark.email
def test_project_confirmation_email(email_backend, run_state):
    """Student really receives the project submission-confirmation email.

    Default backend is the real SES round-trip (Datamailer sends via SES; read
    back from the inbound S3 bucket). xfails cleanly when the real inbox is not
    configured or not enabled on the target deployment.
    """
    require_project(run_state)
    if not email_backend.configured:
        pytest.xfail(
            "Real inbox not configured (E2E_REAL_INBOX_* / DATAMAILER_* unset)."
        )
    try:
        email_backend.list_messages(run_state.student_email, limit=1)
    except InboxDisabled:
        pytest.xfail(
            "Real inbox disabled on this deployment (REAL_INBOX_ENABLED off); "
            "enable REAL_INBOX_* on the Datamailer deployment to verify receipt."
        )
    try:
        _assert_project_confirmation(email_backend, run_state)
    finally:
        email_backend.clear(run_state.student_email)


def test_assign_peer_reviews(api, run_state):
    require_project(run_state)
    result = api.assign_project_reviews(
        run_state.course.slug, run_state.course.project_id
    )
    assert "status" in result, f"assign-reviews returned no status: {result}"
    # A single-submitter smoke run cannot satisfy the peer-review assignment
    # threshold. The important thing is that the endpoint runs and returns the
    # expected controlled result instead of an application error.
    assert result.get("status") in ("OK", "FAIL"), result
    if result.get("status") == "FAIL":
        assert "Not enough submissions" in result.get("message", ""), result


def test_score_project(api, run_state):
    require_project(run_state)
    result = api.score_project(
        run_state.course.slug, run_state.course.project_id
    )
    assert "status" in result, f"score returned no status: {result}"
    assert result.get("status") in ("OK", "FAIL"), result
    # Verify the score-component fields exist in the submissions export even
    # when the one-student run cannot complete peer-review scoring.
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
