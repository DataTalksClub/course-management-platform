import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

from .client_campaigns import DatamailerCampaignClient
from .client_contacts import DatamailerContactClient
from .client_recipient_lists import DatamailerRecipientListClients
from .client_transactional import DatamailerTransactionalClient
from .client_types import DatamailerRequestData


@dataclass(frozen=True)
class DatamailerConfig:
    url: str
    api_key: str
    client: str
    audience: str
    from_email: str = ""
    strict: bool = False

    @classmethod
    def from_settings(cls) -> "DatamailerConfig | None":
        url = getattr(settings, "DATAMAILER_URL", "")
        api_key = getattr(settings, "DATAMAILER_API_KEY", "")
        client = getattr(settings, "DATAMAILER_CLIENT", "")
        audience = getattr(settings, "DATAMAILER_AUDIENCE", "")
        from_email = getattr(settings, "DATAMAILER_FROM_EMAIL", "")

        if not all([url, api_key, client, audience]):
            return None

        strict = getattr(settings, "DATAMAILER_STRICT", False)
        normalized_url = url.rstrip("/")
        return cls(
            url=normalized_url,
            api_key=api_key,
            client=client,
            audience=audience,
            from_email=from_email,
            strict=strict,
        )


class DatamailerClient:
    def __init__(
        self,
        config: DatamailerConfig,
        session: requests.Session | None = None,
    ):
        self.config = config
        self.session = session or requests.Session()
        self.contacts = DatamailerContactClient(config, self.request)
        self.recipient_lists = DatamailerRecipientListClients(
            config,
            self.request,
        )
        self.transactional = DatamailerTransactionalClient(
            config,
            self.request,
        )
        self.campaigns = DatamailerCampaignClient(config, self.request)

    def request(self, data: DatamailerRequestData) -> dict[str, Any] | None:
        url = f"{self.config.url}{data.path}"
        request_kwargs: dict[str, Any] = {
            "json": data.json,
            "timeout": 10,
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


def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None


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
