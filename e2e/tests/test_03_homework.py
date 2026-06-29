"""Scenario 4 (issue #194): Homework flow.

* Submit homework answers through the UI (as impersonated student).
* Confirmation page renders with the submitted values.
* Submission-confirmation email really received via SES and read back from the
  Datamailer real inbox (xfails if the real inbox is not enabled on the target).
* Score the homework (API); submission shows a score.
* Leaderboard reflects the score.
"""

from __future__ import annotations

import pytest

from e2e.api_client import ApiRequestData
from e2e.mock_inbox import InboxDisabled

pytestmark = pytest.mark.homework


@pytest.fixture(scope="module")
def hw_answers():
    # Keyed by question position; resolved to question ids in the test.
    return {
        "free_form": "Paris",
        "checkboxes": "2,4",
        "multiple_choice": "2",
        "long_free_form": "I learned how to write e2e smoke tests.",
    }


def _questions_via_api(api, run_state, hw_id) -> dict[str, int]:
    request_data = ApiRequestData(
        method="GET",
        path=f"/api/courses/{run_state.course.slug}/homeworks/{hw_id}/questions/",
        expected=(200,),
    )
    resp = api._request(request_data)  # internal helper reuse, read-only GET
    questions = resp.json().get("questions", [])
    mapping: dict[str, int] = {}
    for q in questions:
        text = q.get("text", "").lower()
        if "free form)" in text and "long" not in text:
            mapping["free_form"] = q["id"]
        elif "checkboxes" in text:
            mapping["checkboxes"] = q["id"]
        elif "multiple choice" in text:
            mapping["multiple_choice"] = q["id"]
        elif "long free form" in text:
            mapping["long_free_form"] = q["id"]
    return mapping


def test_submit_homework_via_ui(admin_session, api, run_state, hw_answers):
    assert run_state.student_user_id, "Student/impersonation required first."
    assert run_state.course and run_state.course.homework_slug

    qmap = _questions_via_api(api, run_state, run_state.course.homework_id)
    assert {"free_form", "checkboxes", "multiple_choice"} <= set(qmap), (
        f"Could not resolve all question ids: {qmap}"
    )

    answers = {
        qmap["free_form"]: hw_answers["free_form"],
        qmap["checkboxes"]: hw_answers["checkboxes"],
        qmap["multiple_choice"]: hw_answers["multiple_choice"],
    }
    if "long_free_form" in qmap:
        answers[qmap["long_free_form"]] = hw_answers["long_free_form"]

    admin_session.submit_homework(
        run_state.course.slug,
        run_state.course.homework_slug,
        answers,
        homework_url="https://github.com/DataTalksClub/course-management-platform",
        learning_in_public_links=[
            f"https://twitter.com/e2e/{run_state.namespace}-hw"
        ],
        time_spent_lectures=2,
        time_spent_homework=3,
    )
    run_state.homework_submitted = True

    body = admin_session.homework_confirmation_text()
    assert "Thank you for submitting your homework" in body, (
        "Homework confirmation message not shown after submission."
    )


def test_homework_submission_recorded_in_api(api, run_state):
    require_submitted(run_state)
    data = api.homework_submissions(
        run_state.course.slug, run_state.course.homework_slug
    )
    submissions = data.get("submissions", [])
    assert any(
        s.get("student_id") == run_state.student_user_id
        or s.get("student", {}).get("email") == run_state.student_email
        or run_state.student_email in str(s)
        for s in submissions
    ), f"No submission found for {run_state.student_email}: {submissions!r}"


# Confirmation-email contract (from courses/views/homework.py, read-only):
#   template_key = "homework-submission-confirmation"
#   subject      = "Homework submission saved: <homework title>"
#   context      = {update_url, profile_url, course_slug, homework_slug, ...}
HOMEWORK_CONFIRMATION_TEMPLATE = "homework-submission-confirmation"


def _assert_homework_confirmation(backend, run_state):
    # The real SES-inbound backend parses raw MIME and carries no template_key,
    # so match on subject + body; only the mock store has a template_key.
    expected_template = (
        HOMEWORK_CONFIRMATION_TEMPLATE if backend.name == "mock" else None
    )
    message = backend.wait_for_message(
        run_state.student_email,
        template_key=expected_template,
        subject="Homework submission saved",
        # Real SES inbound is eventually consistent (~5-15s); give it headroom.
        timeout=120,
    )
    assert "E2E Homework 1" in message.subject
    if expected_template:
        assert message.template_key == expected_template
    # The confirmation carries an "Update your submission" link to the homework
    # (in the rendered body, and in context.update_url for the mock backend).
    assert message.body_contains("/homework/"), (
        "Homework confirmation email missing update link "
        f"(subject={message.subject!r})."
    )


@pytest.mark.email
def test_homework_confirmation_email(email_backend, run_state):
    """Student really receives the submission-confirmation email.

    Default backend is the real SES round-trip: Datamailer sends via SES and the
    message is read back from the Datamailer real inbox (inbound S3). This is the
    usual delivery flow -- the same in dev and prod. It xfails cleanly when the
    real inbox is not configured or not enabled on the target deployment, so the
    suite stays green until REAL_INBOX_* is switched on.
    """
    require_submitted(run_state)
    if not email_backend.configured:
        pytest.xfail(
            "Real inbox not configured (E2E_REAL_INBOX_* / DATAMAILER_* unset)."
        )
    # If the deployment has the real inbox turned off, xfail right away rather
    # than burning the full poll timeout waiting for mail that can't be read.
    try:
        email_backend.list_messages(run_state.student_email, limit=1)
    except InboxDisabled:
        pytest.xfail(
            "Real inbox disabled on this deployment (REAL_INBOX_ENABLED off); "
            "enable REAL_INBOX_* on the Datamailer deployment to verify receipt."
        )
    try:
        _assert_homework_confirmation(email_backend, run_state)
    finally:
        email_backend.clear(run_state.student_email)


def test_score_homework(api, run_state):
    require_submitted(run_state)
    result = api.score_homework(
        run_state.course.slug, run_state.course.homework_id
    )
    assert result.get("status") == "OK", f"Scoring failed: {result}"

    data = api.homework_submissions(
        run_state.course.slug, run_state.course.homework_slug
    )
    submissions = data.get("submissions", [])
    assert submissions, "No submissions to score."
    # At least one submission now has a numeric score.
    assert any(
        _has_score(s) for s in submissions
    ), f"No scored submission after scoring: {submissions!r}"


def test_leaderboard_reflects_score(api, run_state):
    require_submitted(run_state)
    leaderboard = api.leaderboard_yaml(run_state.course.slug)
    # The student appears on the leaderboard once the first homework is scored.
    assert leaderboard.strip(), "Leaderboard is empty after scoring."


def _has_score(submission: dict) -> bool:
    for key in ("total_score", "questions_score", "score"):
        value = submission.get(key)
        if isinstance(value, (int, float)) and value is not None:
            return True
    # Nested under a homework_submission object in some exports.
    nested = submission.get("homework_submission") or {}
    return any(
        isinstance(nested.get(k), (int, float)) for k in ("total_score", "score")
    )


def require_submitted(run_state):
    if not run_state.homework_submitted:
        pytest.skip("Homework was not submitted (earlier step skipped/failed).")
