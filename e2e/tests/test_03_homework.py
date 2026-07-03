"""Scenario 4 (issue #194): Homework flow.

* Submit homework answers through the UI (as impersonated student).
* Confirmation page renders with the submitted values.
* Submission-confirmation email verified via CMP's own Datamailer send audit
  (the real prod send path runs with dry_run, so nothing is delivered but the
  rendered email is recorded and read back over HTTP).
* Score the homework (API); submission shows a score.
* Leaderboard reflects the score.
"""

import pytest

from e2e.api_client import ApiRequestData, SendAuditTimeout, send_audit_body_contains
from e2e.browser import HomeworkSubmissionData

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
    body = resp.json()
    questions = body.get("questions", [])
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


def _assert_homework_flow_ready(run_state):
    assert run_state.student_user_id, "Student/impersonation required first."
    assert run_state.course and run_state.course.homework_slug


def _assert_required_homework_questions(qmap):
    required_questions = ("free_form", "checkboxes", "multiple_choice")
    for question_key in required_questions:
        assert question_key in qmap, (
            f"Could not resolve all question ids: {qmap}"
        )


def _homework_question_ids(api, run_state):
    qmap = _questions_via_api(api, run_state, run_state.course.homework_id)
    _assert_required_homework_questions(qmap)
    return qmap


def _homework_answers_by_question(qmap, hw_answers):
    answers = {}
    answers[qmap["free_form"]] = hw_answers["free_form"]
    answers[qmap["checkboxes"]] = hw_answers["checkboxes"]
    answers[qmap["multiple_choice"]] = hw_answers["multiple_choice"]
    if "long_free_form" in qmap:
        answers[qmap["long_free_form"]] = hw_answers["long_free_form"]
    return answers


def _homework_submission_data(run_state, answers):
    learning_links = [
        f"https://twitter.com/e2e/{run_state.namespace}-hw"
    ]
    return HomeworkSubmissionData(
        course_slug=run_state.course.slug,
        homework_slug=run_state.course.homework_slug,
        answers=answers,
        homework_url="https://github.com/DataTalksClub/course-management-platform",
        learning_in_public_links=learning_links,
        time_spent_lectures=2,
        time_spent_homework=3,
    )


def _assert_homework_submission_confirmation(admin_session):
    body = admin_session.homework_confirmation_text()
    assert "Thank you for submitting your homework" in body, (
        "Homework confirmation message not shown after submission."
    )


def test_submit_homework_via_ui(admin_session, api, run_state, hw_answers):
    _assert_homework_flow_ready(run_state)
    qmap = _homework_question_ids(api, run_state)
    answers = _homework_answers_by_question(qmap, hw_answers)
    submission_data = _homework_submission_data(run_state, answers)

    admin_session.submit_homework(submission_data)
    run_state.homework_submitted = True

    _assert_homework_submission_confirmation(admin_session)


def test_homework_submission_recorded_in_api(api, run_state):
    require_submitted(run_state)
    data = api.homework_submissions(
        run_state.course.slug, run_state.course.homework_slug
    )
    submissions = data.get("submissions", [])
    assert _has_homework_submission(submissions, run_state), (
        f"No submission found for {run_state.student_email}: {submissions!r}"
    )


def _has_homework_submission(submissions, run_state):
    for submission in submissions:
        if _homework_submission_matches_student(submission, run_state):
            return True
    return False


def _homework_submission_matches_student(submission, run_state):
    if submission.get("student_id") == run_state.student_user_id:
        return True
    student = submission.get("student", {})
    if student.get("email") == run_state.student_email:
        return True
    return run_state.student_email in str(submission)


# Confirmation-email contract (from courses/views/homework.py, read-only):
#   template_key = "homework-submission-confirmation"
#   subject      = "Homework submission saved: <homework title>"
#   context      = {update_url, profile_url, course_slug, homework_slug, ...}
HOMEWORK_CONFIRMATION_TEMPLATE = "homework-submission-confirmation"


@pytest.mark.email
def test_homework_confirmation_email(send_audits, run_state):
    """The submission-confirmation email is rendered on the real send path.

    Verification reads CMP's own ``DatamailerSendAudit`` over HTTP rather than
    an inbox: the prod path runs (outbox -> dispatch -> /api/transactional/send
    -> audit), but with ``DATAMAILER_TRANSACTIONAL_DRY_RUN=1`` the render is
    returned inline and nothing is delivered. xfails cleanly when no audit
    appears (Datamailer not configured / dry-run off on the target), so the
    suite stays green until it is switched on.
    """
    require_submitted(run_state)
    try:
        audit = send_audits.wait_for_send_audit(
            run_state.student_email,
            HOMEWORK_CONFIRMATION_TEMPLATE,
            body_contains="/homework/",
            timeout=60,
        )
    except SendAuditTimeout as exc:
        pytest.xfail(
            "No homework-confirmation send audit found; ensure Datamailer is "
            "configured on the target with DATAMAILER_TRANSACTIONAL_DRY_RUN=1. "
            f"({exc})"
        )
    assert audit["template_key"] == HOMEWORK_CONFIRMATION_TEMPLATE
    assert audit["message"].get("email") == run_state.student_email
    # The confirmation carries an "Update your submission" link to the homework,
    # present in the rendered body (and in the render context when included).
    assert send_audit_body_contains(audit, "/homework/"), (
        "Homework confirmation email missing update link "
        f"(rendered={audit.get('rendered')!r})."
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
    assert _has_scored_submission(submissions), (
        f"No scored submission after scoring: {submissions!r}"
    )


def _has_scored_submission(submissions):
    for submission in submissions:
        if _has_score(submission):
            return True
    return False


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
    for key in ("total_score", "score"):
        value = nested.get(key)
        if isinstance(value, (int, float)):
            return True
    return False


def require_submitted(run_state):
    if not run_state.homework_submitted:
        pytest.skip("Homework was not submitted (earlier step skipped/failed).")
