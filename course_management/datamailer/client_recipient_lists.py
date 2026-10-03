from typing import Any

from .client_chunking import chunk_payload_by_members
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
        # Chunked so large member syncs stay under the relay WAF body limit;
        # chunk responses have their counts aggregated.
        chunks = chunk_payload_by_members(payload)
        response: dict[str, Any] | None = None
        totals: dict[str, int] = {}
        for chunk in chunks:
            request_data = DatamailerRequestData(
                method="POST",
                path=f"/api/recipient-lists/{list_key}/members/bulk-upsert",
                json=chunk,
            )
            response = self.request(request_data)
            if response is None:
                continue
            for key in ("created_count", "updated_count"):
                value = response.get(key)
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value
        if response is not None and len(chunks) > 1:
            response = {**response, **totals}
        return response

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
        # Chunked so large reminder sends stay under the relay WAF body limit;
        # member idempotency keys make split requests safe, and chunk response
        # counts are aggregated.
        chunks = chunk_payload_by_members(payload)
        response: dict[str, Any] | None = None
        totals: dict[str, int] = {}
        count_keys = (
            "created_count",
            "enqueued_count",
            "skipped_count",
            "idempotent_replay_count",
        )
        nested_count_keys = ("member_count", "active_member_count")
        for chunk in chunks:
            request_data = DatamailerRequestData(
                method="POST",
                path="/api/transient-recipient-lists/transactional-send",
                json=chunk,
            )
            response = self.request(request_data)
            if response is None:
                continue
            for key in count_keys:
                value = response.get(key)
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value
            transient_list = response.get("transient_recipient_list") or {}
            for key in nested_count_keys:
                value = transient_list.get(key)
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value
        if response is not None and len(chunks) > 1:
            aggregated = {**response, **totals}
            transient_list = dict(
                response.get("transient_recipient_list") or {}
            )
            for key in nested_count_keys:
                if key in totals:
                    transient_list[key] = totals[key]
            aggregated["transient_recipient_list"] = transient_list
            response = aggregated
        return response
