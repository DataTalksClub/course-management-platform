"""Runtime configuration for the e2e smoke suite.

Everything sensitive (admin password, API token) comes from environment
variables / CI secrets. Nothing is hardcoded. Loading order:

1. Process environment (CI secrets).
2. ``e2e/.env`` if present (local convenience, gitignored).
3. The repo-root ``.env`` (dev API token + base URLs live here already).

Required vars are validated lazily so that ``--collect-only`` and the
health-check test can run even when full credentials are missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Namespace prefix used for every resource the suite creates. The pre-run
# sweep and post-run assertions key off this exact string, so do not change
# it without updating the teardown logic.
NAMESPACE_PREFIX = "e2e-smoke-"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency).

    Only sets keys that are not already present in the environment, so real
    CI secrets always win over file values.
    """
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _ensure_env_loaded() -> None:
    _load_dotenv(Path(__file__).resolve().parent / ".env")
    _load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when a required configuration value is missing."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_token: str | None
    admin_email: str | None
    admin_password: str | None
    student_email: str | None
    student_password: str | None
    mock_inbox_url: str | None
    mock_inbox_api_key: str | None
    mock_inbox_domain: str
    mock_inbox_tag: str
    real_inbox_url: str | None
    real_inbox_api_key: str | None
    request_timeout: float
    ui_timeout_ms: int
    expected_version: str | None

    def mock_address(self, label: str) -> str:
        """Build a plus-tagged mock address the Datamailer mock inbox captures.

        Shape: ``<tag>+<label>@<domain>`` (e.g. ``e2e+e2e-smoke-123@mailbox.test``).
        The datamailer side recognises an address as "mock" when its domain is
        ``MOCK_INBOX_DOMAIN`` *or* its local part carries ``MOCK_INBOX_PLUS_TAG``.
        Using both keeps it a mock address regardless of which check fires.
        """
        clean = "".join(c if (c.isalnum() or c in "-._") else "-" for c in label)
        return f"{self.mock_inbox_tag}+{clean}@{self.mock_inbox_domain}"

    def require_api_token(self) -> str:
        if not self.api_token:
            raise ConfigError(
                "E2E_API_TOKEN (or DEV_AUTH_TOKEN in .env) is required for "
                "API provisioning/teardown but was not set."
            )
        return self.api_token

    def require_admin(self) -> tuple[str, str]:
        if not self.admin_email or not self.admin_password:
            raise ConfigError(
                "E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for the "
                "browser flows (admin login + impersonation) but were not set."
            )
        return self.admin_email, self.admin_password


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def load_settings() -> Settings:
    _ensure_env_loaded()

    # Default to dev; PUBLIC_BASE_URL in the repo .env already points at dev.
    base_url = _first_env(
        "E2E_BASE_URL", "PUBLIC_BASE_URL"
    ) or "https://dev.courses.datatalks.club"
    base_url = base_url.rstrip("/")

    return Settings(
        base_url=base_url,
        # Prefer an explicit e2e token; fall back to the dev token in .env.
        api_token=_first_env("E2E_API_TOKEN", "DEV_AUTH_TOKEN"),
        admin_email=_first_env("E2E_ADMIN_EMAIL"),
        admin_password=_first_env("E2E_ADMIN_PASSWORD"),
        student_email=_first_env("E2E_STUDENT_EMAIL"),
        student_password=_first_env("E2E_STUDENT_PASSWORD"),
        # Mock inbox: base URL is the Datamailer service root (the client
        # appends /api/mock-inbox/...). Fall back to the datamailer settings
        # already present in the repo .env.
        mock_inbox_url=_first_env("E2E_MOCK_INBOX_URL", "DATAMAILER_URL"),
        mock_inbox_api_key=_first_env(
            "E2E_MOCK_INBOX_API_KEY", "DATAMAILER_API_KEY"
        ),
        mock_inbox_domain=(
            _first_env("E2E_MOCK_INBOX_DOMAIN", "MOCK_INBOX_DOMAIN")
            or "mailbox.test"
        ),
        mock_inbox_tag=(
            _first_env("E2E_MOCK_INBOX_TAG", "MOCK_INBOX_PLUS_TAG") or "e2e"
        ),
        # Real SES-inbound backend (issue-194-ses-inbound). Unset until ready;
        # the one/two tests using it skip/xfail.
        real_inbox_url=_first_env("E2E_REAL_INBOX_URL"),
        real_inbox_api_key=_first_env("E2E_REAL_INBOX_API_KEY"),
        request_timeout=float(_first_env("E2E_REQUEST_TIMEOUT") or "30"),
        ui_timeout_ms=int(_first_env("E2E_UI_TIMEOUT_MS") or "20000"),
        expected_version=_first_env("E2E_EXPECTED_VERSION"),
    )
