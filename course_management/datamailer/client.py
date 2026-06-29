from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings


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
        return cls(
            url=url.rstrip("/"),
            api_key=api_key,
            client=client,
            audience=audience,
            from_email=from_email,
            strict=strict,
        )


@dataclass(frozen=True)
class DatamailerRequestData:
    method: str
    path: str
    json: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class DatamailerClient:
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

    def upsert_contact(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/contacts",
            json=payload,
        )
        return self.request(request_data)

    def bulk_import_contacts(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/contacts/imports",
            json=payload,
        )
        return self.request(request_data)

    def send_transactional(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/transactional/send",
            json=payload,
        )
        return self.request(request_data)

    def contact_status(self, email: str) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path="/api/contacts/status",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def erase_contact(self, email: str) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/contacts/erase",
            json={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def contact_history(
        self,
        contact_id: int,
        *,
        limit: int = 25,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/contacts/{contact_id}/history",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
                "limit": limit,
            },
        )
        return self.request(request_data)

    def transactional_message_status(
        self,
        message_id: int,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/transactional/messages/{message_id}",
        )
        return self.request(request_data)

    def contact_preferences(
        self,
        email: str,
        *,
        category_tags: list[str],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path="/api/contacts/preferences",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
                "category_tags": ",".join(category_tags),
            },
        )
        return self.request(request_data)

    def update_contact_preferences(
        self,
        email: str,
        categories: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="PUT",
            path="/api/contacts/preferences",
            json={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
                "categories": categories,
            },
        )
        return self.request(request_data)

    def upsert_recipient_list_member(
        self,
        list_key: str,
        source_object_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="PUT",
            path=f"/api/recipient-lists/{list_key}/members/{source_object_key}",
            json=payload,
        )
        return self.request(request_data)

    def remove_recipient_list_member(
        self,
        list_key: str,
        source_object_key: str,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="DELETE",
            path=f"/api/recipient-lists/{list_key}/members/{source_object_key}",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def recipient_list_members(
        self,
        list_key: str,
        *,
        include_removed: bool = False,
        limit: int = 10000,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/recipient-lists/{list_key}/members",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
                "include_removed": "true" if include_removed else "false",
                "limit": limit,
            },
        )
        return self.request(request_data)

    def bulk_upsert_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/recipient-lists/{list_key}/members/bulk-upsert",
            json=payload,
        )
        return self.request(request_data)

    def reconcile_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/recipient-lists/{list_key}/members/reconcile",
            json=payload,
        )
        return self.request(request_data)

    def create_recipient_list_import(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/recipient-lists/{list_key}/imports",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            }
            | payload,
        )
        return self.request(request_data)

    def recipient_list_import(
        self,
        list_key: str,
        job_id: int,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/recipient-lists/{list_key}/imports/{job_id}",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def send_recipient_list_transactional(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/recipient-lists/{list_key}/transactional-send",
            json=payload,
        )
        return self.request(request_data)

    def send_transient_recipient_list_transactional(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/transient-recipient-lists/transactional-send",
            json=payload,
        )
        return self.request(request_data)

    def upsert_campaign(
        self,
        external_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="PUT",
            path=f"/api/campaigns/{external_key}",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            }
            | payload,
        )
        return self.request(request_data)

    def campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/campaigns/{external_key}",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def queue_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/campaigns/{external_key}/queue",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def cancel_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/campaigns/{external_key}/cancel",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def preview_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/campaigns/{external_key}/preview",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )
        return self.request(request_data)

    def test_send_campaign(
        self,
        external_key: str,
        emails: list[str],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path=f"/api/campaigns/{external_key}/test-send",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
                "emails": emails,
            },
        )
        return self.request(request_data)

def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None

def public_url(path: str) -> str:
    base_url = getattr(settings, "PUBLIC_BASE_URL", "")
    if not base_url:
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
