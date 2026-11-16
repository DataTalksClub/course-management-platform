import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

from course_management.relay.retry_policy import (
    is_rate_limit_error,
    is_retryable_relay_http_error,
    retry_after_seconds,
)

from .client_campaigns import DatamailerCampaignClient
from .client_contacts import DatamailerContactClient
from .client_pacing import PacedMemberRequest
from .client_recipient_lists import DatamailerRecipientListClients
from .client_transactional import DatamailerTransactionalClient
from .client_types import DatamailerRequestData

logger = logging.getLogger(__name__)

# Bulk sends post the whole recipient list inline, so they need far longer
# than a single transactional message. This is not just a false-failure
# problem: when we hang up early Relay abandons the dispatch it was
# midway through, and every message it had created but not yet sent stays
# "queued" forever with no error and no retry. A July 2026 reminder run
# delivered to exactly one recipient -- the first in the list -- and
# stranded the rest.
DEFAULT_TIMEOUT_SECONDS = 60.0

RELAY_CONFIG_MISSING = "relay_config_missing"
RELAY_CONFIG_INVALID = "relay_config_invalid"


def is_production() -> bool:
    """Return True if the current environment is production."""
    env = (
        getattr(settings, "ENVIRONMENT", None)
        or getattr(settings, "OBSERVABILITY_ENVIRONMENT", None)
        or ""
    ).lower().strip()
    # The private production release and its public rolling follower retain
    # the historical "staging" environment (deploy/coolify/README.md).
    # The isolated development service uses "dev".
    return env in ("production", "prod", "staging")


def _valid_relay_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        # Accessing hostname/port also validates malformed IPv6 and ports.
        return bool(
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and (parsed.port is None or parsed.port > 0)
        )
    except ValueError:
        return False


def validate_relay_config() -> tuple[bool, str, "DatamailerConfig | None"]:
    """Validate Relay settings and build DatamailerConfig if valid.

    Returns:
        (is_valid, error_reason, config_or_none)
    """
    url = (getattr(settings, "RELAY_URL", "") or "").strip()
    api_key = (getattr(settings, "RELAY_API_KEY", "") or "").strip()
    client = (getattr(settings, "RELAY_CLIENT", "") or "").strip()
    audience = (getattr(settings, "RELAY_AUDIENCE", "") or "").strip()

    if not api_key:
        return False, RELAY_CONFIG_MISSING, None
    if not url:
        return False, RELAY_CONFIG_MISSING, None
    if not client or not audience:
        return False, RELAY_CONFIG_MISSING, None

    if not _valid_relay_url(url):
        return False, RELAY_CONFIG_INVALID, None

    config = DatamailerConfig.from_settings()
    if config is None:
        return False, RELAY_CONFIG_MISSING, None

    return True, "", config


def get_relay_health_status() -> dict[str, Any]:
    """Check Relay configuration and operational health.

    Returns dict with status, error, relay_config, dry_run, dry_run_on_prod.
    """
    is_valid, reason, _config = validate_relay_config()
    is_prod = is_production()
    dry_run = bool(getattr(settings, "RELAY_TRANSACTIONAL_DRY_RUN", False))
    dry_run_on_prod = is_prod and dry_run

    if not is_valid:
        return {
            "status": "FAIL",
            "error": reason,
            "relay_config": "invalid" if reason == RELAY_CONFIG_INVALID else "missing",
            "dry_run": dry_run,
            "dry_run_on_prod": dry_run_on_prod,
        }

    if dry_run_on_prod:
        return {
            "status": "FAIL",
            "error": "RELAY_TRANSACTIONAL_DRY_RUN enabled on prod",
            "relay_config": "ok",
            "dry_run": dry_run,
            "dry_run_on_prod": True,
        }

    return {
        "status": "ok",
        "error": "",
        "relay_config": "ok",
        "dry_run": dry_run,
        "dry_run_on_prod": False,
    }


@dataclass(frozen=True)
class DatamailerConfig:
    url: str
    api_key: str
    client: str
    audience: str
    from_email: str = ""
    strict: bool = False
    transactional_dry_run: bool = False
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_settings(cls) -> "DatamailerConfig | None":
        url = (getattr(settings, "RELAY_URL", "") or "").strip()
        api_key = (getattr(settings, "RELAY_API_KEY", "") or "").strip()
        client = (getattr(settings, "RELAY_CLIENT", "") or "").strip()
        audience = (getattr(settings, "RELAY_AUDIENCE", "") or "").strip()
        from_email = (getattr(settings, "RELAY_FROM_EMAIL", "") or "").strip()

        if not all([url, api_key, client, audience]):
            return None

        if not _valid_relay_url(url):
            return None

        strict = getattr(settings, "RELAY_STRICT", False)
        transactional_dry_run = getattr(
            settings, "RELAY_TRANSACTIONAL_DRY_RUN", False
        )
        timeout = getattr(
            settings,
            "RELAY_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        )
        normalized_url = url.rstrip("/")
        return cls(
            url=normalized_url,
            api_key=api_key,
            client=client,
            audience=audience,
            from_email=from_email,
            strict=strict,
            transactional_dry_run=transactional_dry_run,
            timeout=timeout,
        )


class DatamailerClient:
    def __init__(
        self,
        config: DatamailerConfig,
        session: requests.Session | None = None,
        *,
        pacer: Any = None,
        max_retries: int = 0,
    ):
        self.config = config
        self.session = session or requests.Session()
        self.max_retries = max(0, int(max_retries))
        self.pacer = pacer
        paced_once = (
            pacer.wrap(self._send_once)
            if pacer is not None
            else PacedMemberRequest(self._send_once)
        )
        self.paced_request = lambda data: self._send_with_retry(
            data, paced_once
        )
        self.contacts = DatamailerContactClient(config, self.paced_request)
        self.recipient_lists = DatamailerRecipientListClients(
            config,
            self.request,
            paced_request=self.paced_request,
        )
        self.transactional = DatamailerTransactionalClient(
            config,
            self.request,
        )
        self.campaigns = DatamailerCampaignClient(config, self.request)

    def _retry_delay_seconds(self, exc: requests.HTTPError, attempt: int) -> float:
        if is_rate_limit_error(exc):
            retry_after = retry_after_seconds(exc) or 0.0
            return max(retry_after, min(300.0, 30.0 * (2**attempt)))
        return min(60.0, 2.0 * (2**attempt))

    def _send_with_retry(
        self,
        data: DatamailerRequestData,
        sender: Any,
    ) -> dict[str, Any] | None:
        for attempt in range(self.max_retries + 1):
            try:
                return sender(data)
            except requests.HTTPError as exc:
                if (
                    attempt >= self.max_retries
                    or not is_retryable_relay_http_error(exc)
                ):
                    raise
                delay = self._retry_delay_seconds(exc, attempt)
                logger.warning(
                    "Retryable Relay error on %s %s (attempt %s/%s); "
                    "sleeping %.1fs: %s",
                    data.method,
                    data.path,
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
        return None

    def _send_once(self, data: DatamailerRequestData) -> dict[str, Any] | None:
        url = f"{self.config.url}{data.path}"
        request_kwargs: dict[str, Any] = {
            "json": data.json,
            "timeout": self.config.timeout,
            "headers": {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        }
        if data.params is not None:
            request_kwargs["params"] = data.params

        response = self.session.request(
            data.method,
            url,
            **request_kwargs,
        )
        response.raise_for_status()

        if not response.content:
            return None

        return response.json()

    def request(self, data: DatamailerRequestData) -> dict[str, Any] | None:
        return self._send_with_retry(data, self._send_once)


def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None


def check_relay_availability(timeout: float = 2.0) -> tuple[bool, str]:
    """Check if Relay is configured and ready to accept requests.

    Returns (is_available, error_message).
    """
    config = DatamailerConfig.from_settings()
    if config is None:
        return False, "Relay is not configured"

    readiness_url = f"{config.url}/health/ready"
    try:
        response = requests.get(readiness_url, timeout=timeout)
        if response.status_code == 200:
            return True, ""
        if response.status_code == 503:
            try:
                data = response.json()
                status_str = data.get("status", "not_ready")
            except Exception:
                status_str = "not ready"
            return False, f"Relay service is not ready (status={status_str})"
        if response.status_code == 404:
            fallback_url = f"{config.url}/health/"
            fb_response = requests.get(fallback_url, timeout=timeout)
            if fb_response.status_code == 200:
                return True, ""
            return False, f"Relay returned HTTP {fb_response.status_code}"
        return False, f"Relay returned HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, f"Relay is unreachable ({exc})"


def public_url(path: str) -> str:
    base_url = _notification_base_url()
    normalized_base_url = f"{base_url}/"
    normalized_path = path.lstrip("/")
    return urljoin(normalized_base_url, normalized_path)


def _notification_base_url() -> str:
    """Absolute base URL for links in notification emails.

    Notifications are built without a request, so they can't fall back to the
    request host the way in-app confirmation emails do. If ``PUBLIC_BASE_URL``
    is unset or lacks a scheme/host we must still emit an absolute URL with a
    real host — otherwise emails go out with unusable hostless links like
    ``http:///course-slug/leaderboard``.
    """
    base_url = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        return base_url

    fallback = _fallback_base_url()
    if base_url:
        logger.warning(
            "PUBLIC_BASE_URL=%r has no scheme/host; using %r for "
            "notification links.",
            base_url,
            fallback,
        )
    return fallback


def _fallback_base_url() -> str:
    for host in getattr(settings, "ALLOWED_HOSTS", []):
        if host and host != "*":
            return f"https://{host}"
    return "https://courses.datatalks.club"
