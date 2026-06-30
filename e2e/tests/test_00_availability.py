"""Scenario 1 (issue #194): Availability & auth.

* GET /api/health/ returns {status: ok} (+ expected version when configured).
* Admin login page loads and admin can authenticate via the login form.
* Unauthenticated access to a protected page redirects to login.
"""

import re

import pytest

pytestmark = pytest.mark.smoke


def test_health_endpoint_ok(api, settings):
    body = api.health()
    assert body.get("status") == "ok", f"Health not ok: {body}"
    assert "version" in body, f"Health response missing version: {body}"
    if settings.expected_version:
        assert body["version"] == settings.expected_version, (
            f"Deployed version {body['version']!r} != expected "
            f"{settings.expected_version!r} -- did the deploy finish?"
        )


def test_admin_login_page_loads(admin_page, settings):
    admin_page.goto(f"{settings.base_url}/admin/login/")
    assert admin_page.locator("input[name='username']").count() == 1, (
        "Admin login form (input[name=username]) did not render."
    )
    assert admin_page.locator("input[name='password']").count() == 1


def test_admin_can_authenticate(admin_session, settings):
    # admin_session fixture already logged in via the admin form; confirm the
    # session is authenticated.
    admin_session.page.goto(f"{settings.base_url}/admin/")
    assert "/admin/login" not in admin_session.page.url, (
        "Admin session not authenticated after login."
    )


def test_protected_page_redirects_to_login(admin_page, settings):
    # account settings requires login; from a fresh (unauthenticated) context
    # we expect a redirect to a login page. Use a throwaway context so this is
    # independent of the admin_session login order.
    ctx = admin_page.context.browser.new_context(base_url=settings.base_url)
    page = ctx.new_page()
    try:
        page.goto(f"{settings.base_url}/accounts/settings/")
        # The platform redirects unauthenticated users to its login page
        # (LOGIN_URL is /login/) with a ?next= back to the protected page.
        assert re.search(r"/login(/|\?|$)", page.url) and "next=" in page.url, (
            f"Protected page did not redirect to login; landed on {page.url}"
        )
    finally:
        ctx.close()
