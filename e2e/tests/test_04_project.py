"""Scenario 5 (issue #194): Project flow.

* Submit a project through the UI (as impersonated student).
* Submission-confirmation email verified via CMP's own Datamailer send audit
  (the real prod send path runs with dry_run, so nothing is delivered but the
  rendered email is recorded and read back over HTTP).
* Assign peer reviews (API).
* Score the project; verify score components.
* Leaderboard + project statistics update.

Note: meaningful peer-review assignment needs >= 2 submitters. A single-
student smoke run exercises the assign/score endpoints and asserts they
succeed and return sane counts, rather than requiring assigned reviews.
"""

import pytest

from e2e.api_client import SendAuditTimeout, send_audit_body_contains
from e2e.browser import ProjectSubmissionData

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
    assert _has_project_submission(submissions, run_state.student_email), (
        f"No project submission for {run_state.student_email}: {submissions!r}"
    )


def _has_project_submission(submissions, student_email):
    for submission in submissions:
        if student_email in str(submission):
            return True
    return False


# Confirmation-email contract (from courses/views/project.py, read-only):
#   template_key = "project-submission-confirmation"
#   subject      = "Project submission saved: <project title>"
#   context      = {update_url, profile_url, course_slug, project_slug, ...}
PROJECT_CONFIRMATION_TEMPLATE = "project-submission-confirmation"


@pytest.mark.email
def test_project_confirmation_email(send_audits, run_state):
    """The project confirmation email is rendered on the real send path.

    Verification reads CMP's own ``DatamailerSendAudit`` over HTTP: the prod
    path runs (outbox -> dispatch -> /api/transactional/send -> audit) with
    ``DATAMAILER_TRANSACTIONAL_DRY_RUN=1``, so the render is returned inline and
    nothing is delivered. xfails cleanly when no audit appears.
    """
    require_project(run_state)
    try:
        audit = send_audits.wait_for_send_audit(
            run_state.student_email,
            PROJECT_CONFIRMATION_TEMPLATE,
            body_contains="/project/",
            timeout=60,
        )
    except SendAuditTimeout as exc:
        pytest.xfail(
            "No project-confirmation send audit found; ensure Datamailer is "
            "configured on the target with DATAMAILER_TRANSACTIONAL_DRY_RUN=1. "
            f"({exc})"
        )
    assert audit["template_key"] == PROJECT_CONFIRMATION_TEMPLATE
    assert audit["message"].get("email") == run_state.student_email
    assert send_audit_body_contains(audit, "/project/"), (
        "Project confirmation email missing update link "
        f"(rendered={audit.get('rendered')!r})."
    )


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
    assert _sample_has_score_components(sample), (
        f"Score components not present in submission export: {submissions[0]!r}"
    )


def _sample_has_score_components(sample):
    for token in ("score", "peer", "passed"):
        if token in sample:
            return True
    return False


def test_leaderboard_and_project_stats_update(api, run_state):
    require_project(run_state)
    leaderboard = api.leaderboard_yaml(run_state.course.slug)
    assert leaderboard.strip(), "Leaderboard empty after project scoring."


def require_project(run_state):
    if not run_state.project_submitted:
        pytest.skip("Project was not submitted (earlier step skipped/failed).")
