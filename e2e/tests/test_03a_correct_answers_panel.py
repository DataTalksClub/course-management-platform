"""Cadmin "Correct answers" panel autosave (regression for 2026-11-23 bug).

Ticking correct answers and clicking "Save answers" used to store ",1" /
",1,3" (a hidden empty input was posted next to the checkboxes), and the
panel then rendered every checkbox empty. The panel now autosaves each change.

This scenario provisions its own homework in the run's course (so the scoring
flow in test_03 is untouched) and drives the panel in a separate admin browser
context (the shared admin page is impersonating the student at this point).
"""

import pytest

from e2e.api_client import ApiRequestData
from e2e.browser import AdminSession

pytestmark = pytest.mark.homework

HOMEWORK_SLUG = "hw-correct-answers"


def _questions(api, course_slug, hw_id):
    data = ApiRequestData(
        method="GET",
        path=f"/api/courses/{course_slug}/homeworks/{hw_id}/questions/",
        expected=(200,),
    )
    return {q["text"]: q for q in api._request(data).json()["questions"]}


@pytest.fixture(scope="module")
def answers_homework(api, run_state, due_dates):
    course = run_state.course
    if not course:
        pytest.skip("Course provisioning required first.")
    hw = api.create_homework(
        course.slug,
        {
            "name": "E2E Correct Answers Panel",
            "slug": HOMEWORK_SLUG,
            "due_date": due_dates["homework_due"],
            "description": "Correct answers autosave e2e.",
            "questions": [
                {
                    "text": "Pick the even numbers",
                    "question_type": "CB",
                    "possible_answers": ["1", "2", "3", "4"],
                    "correct_answer": "",
                },
                {
                    "text": "What is 2 + 2?",
                    "question_type": "MC",
                    "possible_answers": ["3", "4", "5"],
                    "correct_answer": "",
                },
                {
                    "text": "Describe the incident",
                    "question_type": "FF",
                    "answer_type": "ANY",
                    "correct_answer": "",
                },
            ],
        },
    )
    return course.slug, hw["id"]


@pytest.fixture(scope="module")
def panel_session(admin_page, admin_creds, settings):
    browser = admin_page.context.browser
    context = browser.new_context(base_url=settings.base_url)
    page = context.new_page()
    page.set_default_timeout(settings.ui_timeout_ms)
    session = AdminSession(page, settings.base_url, settings.ui_timeout_ms)
    session.login_admin(*admin_creds)
    yield session
    context.close()


def _row(page, question_id):
    return page.locator(f'[data-autosave-question="{question_id}"]')


def _expect_saved(page, question_id):
    status = _row(page, question_id).locator("[data-autosave-status]")
    status.filter(has_text="Saved").wait_for(state="visible")


def test_correct_answers_autosave_persists(
    api, panel_session, answers_homework
):
    course_slug, hw_id = answers_homework
    questions = _questions(api, course_slug, hw_id)
    cb = questions["Pick the even numbers"]["id"]
    mc = questions["What is 2 + 2?"]["id"]
    ff = questions["Describe the incident"]["id"]

    page = panel_session.page
    path = f"/cadmin/{course_slug}/homework/{HOMEWORK_SLUG}/submissions"
    panel_session.open(path)
    assert page.get_by_role("button", name="Save answers").count() == 0

    page.check(f"#correct_answer_{cb}_2")
    _expect_saved(page, cb)
    page.check(f"#correct_answer_{cb}_4")
    _expect_saved(page, cb)
    page.check(f"#correct_answer_{mc}_2")
    _expect_saved(page, mc)
    page.fill(f"#correct_answer_{ff}", "No incident to fix.")
    page.locator(f"#correct_answer_{ff}").blur()
    _expect_saved(page, ff)

    stored = _questions(api, course_slug, hw_id)
    assert stored["Pick the even numbers"]["correct_answer"] == "2,4"
    assert stored["What is 2 + 2?"]["correct_answer"] == "2"
    assert stored["Describe the incident"]["correct_answer"] == (
        "No incident to fix."
    )

    page.reload()
    assert page.is_checked(f"#correct_answer_{cb}_2")
    assert page.is_checked(f"#correct_answer_{cb}_4")
    assert not page.is_checked(f"#correct_answer_{cb}_1")
    assert page.is_checked(f"#correct_answer_{mc}_2")
    assert page.input_value(f"#correct_answer_{ff}") == "No incident to fix."

    # Unticking the last option saves an empty answer, not ",".
    page.uncheck(f"#correct_answer_{mc}_2")
    _expect_saved(page, mc)
    assert _questions(api, course_slug, hw_id)["What is 2 + 2?"][
        "correct_answer"
    ] in ("", None)


def test_correct_answers_autosave_failure_is_loud(
    api, panel_session, answers_homework
):
    course_slug, hw_id = answers_homework
    cb = _questions(api, course_slug, hw_id)["Pick the even numbers"]["id"]
    page = panel_session.page
    path = f"/cadmin/{course_slug}/homework/{HOMEWORK_SLUG}/submissions"
    panel_session.open(path)

    reported = []
    page.on(
        "request",
        lambda req: reported.append(req.url)
        if "correct-answers/client-error" in req.url
        else None,
    )
    save_pattern = f"**/questions/{cb}/correct-answer"
    page.route(save_pattern, lambda route: route.abort())
    page.check(f"#correct_answer_{cb}_1")

    row = _row(page, cb)
    row.locator("[data-autosave-status]").filter(
        has_text="Not saved"
    ).wait_for(state="visible")
    alert = page.locator("[data-autosave-alert]")
    alert.wait_for(state="visible")
    assert "NOT saved" in alert.inner_text()
    page.wait_for_timeout(500)
    assert reported, "client failure was not reported to the server"

    page.unroute(save_pattern)
    row.locator("[data-autosave-retry]").click()
    _expect_saved(page, cb)
    alert.wait_for(state="hidden")
    assert _questions(api, course_slug, hw_id)["Pick the even numbers"][
        "correct_answer"
    ] == "1,2,4"
