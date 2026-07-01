from typing import Any

from .client_types import DatamailerRequestData


class DatamailerCampaignClientMixin:
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
