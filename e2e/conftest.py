"""Shared fixtures for the e2e smoke suite.

The suite runs as one ordered scenario (provision -> enroll -> submit ->
score -> verify -> teardown), so most fixtures are session-scoped and a
single ``RunState`` object threads data between test modules. Each test file
maps to a numbered scenario from issue #194 and is named to sort in order.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Allow ``import e2e.<module>`` when pytest is invoked from inside e2e/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from e2e.api_client import CmpApiClient  # noqa: E402
from e2e.config import load_settings, Settings  # noqa: E402
from e2e.mock_inbox import MockInboxClient, RealInboxClient  # noqa: E402
from e2e.provisioning import (  # noqa: E402
    ProvisionedCourse,
    Provisioner,
    make_namespace,
)


@dataclass
class RunState:
    namespace: str
    course: ProvisionedCourse | None = None
    student_email: str | None = None
    student_user_id: int | str | None = None
    teardown_report: dict = field(default_factory=dict)
    # Flags set by earlier scenarios so later ones can skip cleanly.
    homework_submitted: bool = False
    project_submitted: bool = False


@pytest.fixture(scope="session")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="session")
def api(settings: Settings) -> CmpApiClient:
    return CmpApiClient(
        settings.base_url,
        settings.require_api_token(),
        timeout=settings.request_timeout,
    )


@pytest.fixture(scope="session")
def provisioner(api: CmpApiClient) -> Provisioner:
    return Provisioner(api)


@pytest.fixture(scope="session")
def mock_inbox(settings: Settings) -> MockInboxClient:
    return MockInboxClient(settings.mock_inbox_url, settings.mock_inbox_api_key)


@pytest.fixture(scope="session")
def real_inbox(settings: Settings) -> RealInboxClient:
    return RealInboxClient(settings.real_inbox_url, settings.real_inbox_api_key)


@pytest.fixture(scope="session")
def email_backend(request):
    """Resolve the email-verification backend for a test.

    Default = the fast mock-store backend (``mock_inbox``). A test opts into the
    real SES round-trip backend by parametrizing or marking itself with
    ``real`` (``@pytest.mark.real_inbox``); it then resolves to ``real_inbox``.
    Either way, the test gets one object implementing the same interface.
    """
    backend = getattr(request, "param", None)
    if backend is None:
        marker = request.node.get_closest_marker("real_inbox")
        backend = "real" if marker else "mock"
    fixture_name = "real_inbox" if backend == "real" else "mock_inbox"
    return request.getfixturevalue(fixture_name)


@pytest.fixture(scope="session")
def run_state() -> RunState:
    return RunState(namespace=make_namespace(int(time.time())))


@pytest.fixture(scope="session")
def due_dates() -> dict:
    """ISO dates used for homework/project deadlines (well in the future)."""
    future = time.gmtime(time.time() + 90 * 24 * 3600)
    far = time.gmtime(time.time() + 120 * 24 * 3600)
    fmt = "%Y-%m-%d"
    return {
        "homework_due": time.strftime(fmt, future),
        "project_due": time.strftime(fmt, future),
        "peer_review_due": time.strftime(fmt, far),
    }


# -- session-scoped Playwright browser/context/page -----------------------
# pytest-playwright's built-in fixtures are function-scoped; the smoke
# scenario needs one persistent authenticated context across tests, so we
# build our own session-scoped page from the sync API.
@pytest.fixture(scope="session")
def admin_page(settings: Settings):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        pytest.skip("Playwright is not installed")

    headless_env = __import__("os").environ.get("E2E_HEADLESS", "1")
    headless = headless_env not in ("0", "false", "False")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            base_url=settings.base_url,
            ignore_https_errors=False,
        )
        page = context.new_page()
        page.set_default_timeout(settings.ui_timeout_ms)
        yield page
        context.close()
        browser.close()


@pytest.fixture(scope="session")
def admin_creds(settings: Settings):
    """Admin email/password, or skip the test cleanly when not configured.

    Browser-driven scenarios require an admin account; in environments where
    the secret is intentionally absent (e.g. a structural dry run) we skip
    with a clear message rather than erroring.
    """
    if not settings.admin_email or not settings.admin_password:
        pytest.skip(
            "E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD not set; skipping "
            "browser-driven scenario (admin login + impersonation required)."
        )
    return settings.admin_email, settings.admin_password


@pytest.fixture(scope="session")
def admin_session(admin_page, settings: Settings, admin_creds):
    """Authenticated admin browser session (logs in once per session)."""
    from e2e.browser import AdminSession

    email, password = admin_creds
    session = AdminSession(admin_page, settings.base_url, settings.ui_timeout_ms)
    session.login_admin(email, password)
    return session


@pytest.fixture(scope="session")
def optional_admin_session(request, settings: Settings):
    """The admin session if admin creds are configured, else ``None``.

    Teardown and the pre-run sweep delete the course through the admin UI, but
    must still run in the API-only subset (no admin creds) -- there they fall
    back to parking the course hidden. Unlike ``admin_session``, this fixture
    never skips: it returns ``None`` when creds are absent or login fails, so
    callers can degrade gracefully instead of erroring.
    """
    if not settings.admin_email or not settings.admin_password:
        return None
    try:
        return request.getfixturevalue("admin_session")
    except Exception:
        return None


def require(value, message: str):
    """Skip the current test with a clear message when a prereq is missing."""
    if not value:
        pytest.skip(message)
    return value
