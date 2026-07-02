from typing import Any

from .client_types import DatamailerRequest, DatamailerRequestData


class DatamailerRecipientListClients:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.members = DatamailerRecipientListMemberClient(config, request)
        self.imports = DatamailerRecipientListImportClient(config, request)
        self.sends = DatamailerRecipientListSendClient(config, request)


class DatamailerRecipientListMemberClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request

    def upsert(
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

    def remove(
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

    def list_members(
        self,
        list_key: str,
        *,
        include_removed: bool = False,
        limit: int = 10000,
    ) -> dict[str, Any] | None:
        if include_removed:
            include_removed_value = "true"
        else:
            include_removed_value = "false"
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/recipient-lists/{list_key}/members",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
                "include_removed": include_removed_value,
                "limit": limit,
            },
        )
        return self.request(request_data)

    def bulk_upsert(
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

    def reconcile(
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


class DatamailerRecipientListImportClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request

    def create(
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

    def get(
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


class DatamailerRecipientListSendClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request

    def send_to_list(
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

    def send_to_transient_list(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/transient-recipient-lists/transactional-send",
            json=payload,
        )
        return self.request(request_data)
