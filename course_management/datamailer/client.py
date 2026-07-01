from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings

from .client_campaigns import DatamailerCampaignClientMixin
from .client_contacts import DatamailerContactClientMixin
from .client_recipient_lists import DatamailerRecipientListClientMixin
from .client_transactional import DatamailerTransactionalClientMixin
from .client_types import DatamailerRequestData

__all__ = [
    "DatamailerClient",
    "DatamailerConfig",
    "datamailer_enabled",
    "public_url",
]


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


class DatamailerClient(
    DatamailerContactClientMixin,
    DatamailerRecipientListClientMixin,
    DatamailerTransactionalClientMixin,
    DatamailerCampaignClientMixin,
):
    def __init__(
        self,
        config: DatamailerConfig,
        session: requests.Session | None = None,
    ):
        self.config = config
        self.session = session or requests.Session()

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
    base_url = getattr(settings, "PUBLIC_BASE_URL", "")
    if not base_url:
        return path
    normalized_base_url = f"{base_url.rstrip('/')}/"
    normalized_path = path.lstrip("/")
    return urljoin(normalized_base_url, normalized_path)
