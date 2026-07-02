from typing import Any

from .client_types import DatamailerRequest, DatamailerRequestData


class DatamailerContactClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request

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

    def contact_preferences(
        self,
        email: str,
        *,
        category_tags: list[str],
    ) -> dict[str, Any] | None:
        category_tags_param = ",".join(category_tags)
        request_data = DatamailerRequestData(
            method="GET",
            path="/api/contacts/preferences",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
                "category_tags": category_tags_param,
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
