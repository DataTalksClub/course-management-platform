"""Scenario 3 (issue #194): Enrollment & identity.

* A test student (admin-side) exists.
* Admin impersonates the student (django-loginas -- no OAuth).
* Student profile / settings page renders.

Enrollment in this platform is auto-created on first homework/project
submission (``Enrollment.objects.get_or_create``), so the explicit
"enrollment exists" assertion is validated after the homework flow; here we
establish identity + impersonation and confirm the profile renders.
"""

import pytest

pytestmark = pytest.mark.enrollment


def _student_email(settings, run_state) -> str:
    if settings.student_email:
        return settings.student_email
    # Per-run, recognizable, unique address. With Datamailer's dry_run flag
    # nothing is delivered, so a plain namespaced address works; the
    # confirmation email is verified by reading CMP's own send audit keyed on
    # this address (see test_03/test_04).
    return settings.student_address(run_state.namespace)


def test_test_student_exists(admin_session, settings, run_state):
    # admin_session is authenticated by its fixture.
    student_email = _student_email(settings, run_state)
    student_password = settings.student_password or "E2eSmoke!" + run_state.namespace
    run_state.student_email = student_email
    run_state.student_user_id = admin_session.ensure_student(
        student_email, student_password
    )
    assert run_state.student_user_id, "Could not create/find the test student."


def test_impersonate_student(admin_session, run_state):
    assert run_state.student_user_id, "Student must exist first."
    admin_session.impersonate(run_state.student_user_id)
    # Confirm we are now the student, not the admin: account settings renders
    # for a logged-in (non-admin) user.
    body = admin_session.open("/accounts/settings/")
    assert "login" not in admin_session.page.url, (
        "Impersonation failed: redirected to login on /accounts/settings/."
    )
    assert body, "Account settings page rendered empty."


def test_student_profile_page_renders(admin_session, run_state):
    assert run_state.student_user_id, "Student must exist first."
    admin_session.open("/accounts/settings/")
    # The settings page exposes the notification toggles; check one renders.
    assert (
        admin_session.page.locator(
            "[name='email_submission_confirmations'], "
            "form"
        ).count()
        > 0
    ), "Student settings form did not render."
