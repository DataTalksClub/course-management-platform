import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatamailerConfig:
    url: str
    api_key: str
    client: str
    audience: str
    strict: bool = False

    @classmethod
    def from_settings(cls) -> "DatamailerConfig | None":
        url = getattr(settings, "DATAMAILER_URL", "")
        api_key = getattr(settings, "DATAMAILER_API_KEY", "")
        client = getattr(settings, "DATAMAILER_CLIENT", "")
        audience = getattr(settings, "DATAMAILER_AUDIENCE", "")

        if not all([url, api_key, client, audience]):
            return None

        strict = getattr(settings, "DATAMAILER_STRICT", False)
        return cls(
            url=url.rstrip("/"),
            api_key=api_key,
            client=client,
            audience=audience,
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

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.config.url}{path}"
        response = self.session.request(
            method,
            url,
            json=json,
            timeout=10,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        if not response.content:
            return None

        return response.json()

    def upsert_contact(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self.request("POST", "/api/contacts", json=payload)

    def send_transactional(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            "/api/transactional/send",
            json=payload,
        )


def get_datamailer_client() -> DatamailerClient | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None
    return DatamailerClient(config)


def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None


def contact_payload_for_user(user, course=None) -> dict[str, Any] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = []
    custom_fields = {
        "course_platform_user_id": str(user.pk),
        "username": user.username or "",
    }

    if course is not None:
        tags.append(f"course-{course.slug}")
        custom_fields["course_slug"] = course.slug
        custom_fields["course_title"] = course.title

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": tags,
        "custom_fields": custom_fields,
    }


def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        logger.exception(
            "Datamailer contact sync failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise


def send_transactional_email(payload: dict[str, Any]) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.send_transactional(payload)
    except requests.RequestException:
        logger.exception("Datamailer transactional email failed")
        if config.strict:
            raise
        return None
