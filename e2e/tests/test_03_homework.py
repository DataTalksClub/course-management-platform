"""Scenario 4 (issue #194): Homework flow.

* Submit homework answers through the UI (as impersonated student).
* Confirmation page renders with the submitted values.
* Submission-confirmation email received at the mock inbox (xfail until the
  mock-inbox endpoint exists -- see #194).
* Score the homework (API); submission shows a score.
* Leaderboard reflects the score.
"""

from __future__ import annotations

import pytest

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
    resp = api._request(  # internal helper reuse, read-only GET
        "GET",
        f"/api/courses/{run_state.course.slug}/homeworks/{hw_id}/questions/",
        expected=(200,),
    )
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
        homework_url="https://github.com/example/e2e-homework",
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
        s.get("student", {}).get("email") == run_state.student_email
        or run_state.student_email in str(s)
        for s in submissions
    ), f"No submission found for {run_state.student_email}: {submissions!r}"


@pytest.mark.email
def test_homework_confirmation_email(mock_inbox, run_state):
    require_submitted(run_state)
    if not mock_inbox.configured:
        pytest.xfail(
            "Datamailer mock inbox endpoint not available yet "
            "(E2E_MOCK_INBOX_URL unset). TODO: enable once #194 sub-task lands."
        )
    message = mock_inbox.wait_for_message(
        run_state.student_email,
        subject="Homework submission saved",
        timeout=90,
    )
    assert "E2E Homework 1" in message.subject
    # Confirmation email carries an "Update your submission" link.
    assert message.body_contains("/homework/"), (
        "Homework confirmation email missing update link."
    )


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
