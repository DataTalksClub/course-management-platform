"""Runtime configuration for the e2e smoke suite.

Everything sensitive (admin password, API token) comes from environment
variables / CI secrets. Nothing is hardcoded. Loading order:

1. Process environment (CI secrets).
2. ``e2e/.env`` if present (local convenience, gitignored).
3. The repo-root ``.env`` (dev API token lives there already).

Required vars are validated lazily so that ``--collect-only`` and the
health-check test can run even when full credentials are missing.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Namespace prefix used for every resource the suite creates. The pre-run
# sweep and post-run assertions key off this exact string, so do not change
# it without updating the teardown logic.
NAMESPACE_PREFIX = "e2e-smoke-"

# Hard-gate: smoke must only target an explicit loopback origin with a
# throwaway database. Production, current dev, and all other remote targets
# are forbidden until an isolated dev service and database have been
# verified. There is deliberately no override flag. See e2e/safety.py.


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency).

    Only sets keys that are not already present in the environment, so real
    CI secrets always win over file values.
    """
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    for raw in lines:
        key, value = _dotenv_key_value(raw)
        if key:
            _set_env_default(key, value)


def _dotenv_key_value(raw: str) -> tuple[str, str]:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        return "", ""
    separator_index = line.index("=")
    key = line[:separator_index]
    value = line[separator_index + 1 :]
    stripped_key = key.strip()
    stripped_value = value.strip()
    without_double_quotes = stripped_value.strip('"')
    without_quotes = without_double_quotes.strip("'")
    return stripped_key, without_quotes


def _set_env_default(key: str, value: str) -> None:
    if key not in os.environ:
        os.environ[key] = value


def _ensure_env_loaded() -> None:
    _load_dotenv(Path(__file__).resolve().parent / ".env")
    _load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when a required configuration value is missing."""


def _address_label(label: str) -> str:
    characters = []
    for character in label:
        if character.isalnum() or character in "-._":
            safe_character = character
        else:
            safe_character = "-"
        characters.append(safe_character)
    return "".join(characters)


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_token: str | None
    admin_email: str | None
    admin_password: str | None
    student_email: str | None
    student_password: str | None
    request_timeout: float
    ui_timeout_ms: int
    expected_version: str | None

    def student_address(self, label: str) -> str:
        """Build a unique, namespaced student address for a run.

        With Datamailer's ``dry_run`` flag there are no special mock/real
        inbox addresses: nothing is delivered, so any normal address works.
        Email verification reads CMP's own send audit, keyed on this address.
        """
        clean = _address_label(label)
        return f"{clean}@example.com"

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


def _float_env(name: str, default: str) -> float:
    raw_value = _first_env(name) or default
    return float(raw_value)


def _int_env(name: str, default: str) -> int:
    raw_value = _first_env(name) or default
    return int(raw_value)


def assert_safe_e2e_base_url(base_url: str) -> str:
    """Refuse anything but an explicit loopback base URL.

    Only a loopback HTTP(S) origin with a throwaway database is supported
    until an isolated dev service and database have been verified. There is
    deliberately no override flag: production, current dev, and all other
    remote targets are forbidden. See e2e/safety.py.
    """
    from e2e import safety

    try:
        return safety.require_safe_base_url(base_url)
    except safety.ConfigError as exc:
        raise ConfigError(str(exc)) from None


def _base_url() -> str:
    # Fail closed: an explicit E2E_BASE_URL is required. There is no
    # PUBLIC_BASE_URL fallback and no dev default — the suite must never
    # silently run against a live deployment.
    base_url = _first_env("E2E_BASE_URL")
    if not base_url:
        raise ConfigError(
            "E2E_BASE_URL is required (an explicit loopback origin, e.g. "
            "http://127.0.0.1:8000). Refusing to run without a target: "
            "production, current dev, and all other remote targets are "
            "forbidden."
        )
    return assert_safe_e2e_base_url(base_url.rstrip("/"))


def _api_token_from_env() -> str | None:
    """Resolve the staff token from DEV-only env names.

    Never fall back to PROD_* / PRODUCTION_* credential variables — create
    and teardown must not run with production credentials (t1283u).
    """
    return _first_env("E2E_API_TOKEN", "DEV_AUTH_TOKEN")


def load_settings() -> Settings:
    _ensure_env_loaded()

    base_url = _base_url()
    api_token = _api_token_from_env()
    admin_email = _first_env("E2E_ADMIN_EMAIL")
    admin_password = _first_env("E2E_ADMIN_PASSWORD")
    student_email = _first_env("E2E_STUDENT_EMAIL")
    student_password = _first_env("E2E_STUDENT_PASSWORD")
    request_timeout = _float_env("E2E_REQUEST_TIMEOUT", "30")
    ui_timeout_ms = _int_env("E2E_UI_TIMEOUT_MS", "20000")
    expected_version = _first_env("E2E_EXPECTED_VERSION")

    return Settings(
        base_url=base_url,
        api_token=api_token,
        admin_email=admin_email,
        admin_password=admin_password,
        student_email=student_email,
        student_password=student_password,
        request_timeout=request_timeout,
        ui_timeout_ms=ui_timeout_ms,
        expected_version=expected_version,
    )
