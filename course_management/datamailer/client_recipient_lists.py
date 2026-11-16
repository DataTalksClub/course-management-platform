from typing import Any

from .client_chunking import (
    MAX_REQUEST_BODY_BYTES,
    chunk_payload_by_members,
    request_body_size,
)
from .client_pacing import PacedMemberRequest
from .client_types import DatamailerRequest, DatamailerRequestData

# Keep inline /members/reconcile only for small lists; larger lists (1.3k+)
# can exceed CloudFront's origin timeout (504) or WAF's 8 KiB body limit.
RECONCILE_INLINE_MAX_MEMBERS = 100


class DatamailerRecipientListClients:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
        *,
        paced_request: DatamailerRequest | None = None,
    ):
        member_request = paced_request or PacedMemberRequest(request)
        self.members = DatamailerRecipientListMemberClient(
            config, member_request
        )
        self.imports = DatamailerRecipientListImportClient(
            config, member_request
        )
        self.sends = DatamailerRecipientListSendClient(config, request)


class DatamailerRecipientListMemberClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request
        self.member_request = request

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
            response = self.member_request(request_data)
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
        members = payload.get("members") or []
        if (
            len(members) <= RECONCILE_INLINE_MAX_MEMBERS
            and len(chunk_payload_by_members(payload)) == 1
        ):
            request_data = DatamailerRequestData(
                method="POST",
                path=f"/api/recipient-lists/{list_key}/members/reconcile",
                json=payload,
            )
            return self.member_request(request_data)
        return self._chunked_reconcile(list_key, payload)

    def _chunked_reconcile(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # Chunked bulk_upsert + list_members + per-member remove avoids
        # CloudFront origin 504s and 8 KiB WAF body limits on 1.3k+ lists.
        bulk_response = self.bulk_upsert(list_key, payload) or {}
        listed = self.list_members(
            list_key,
            include_removed=False,
            limit=10000,
        ) or {}
        if listed.get("has_more"):
            raise RuntimeError(
                f"Relay list {list_key} has more active members than one page; "
                "refusing a partial reconcile."
            )

        expected_keys = {
            member["source_object_key"]
            for member in (payload.get("members") or [])
            if member.get("source_object_key")
        }
        active_keys = [
            member["source_object_key"]
            for member in (listed.get("members") or [])
            if member.get("status", "active") != "removed"
            and member.get("source_object_key")
        ]
        stale_keys = [key for key in active_keys if key not in expected_keys]
        for source_object_key in stale_keys:
            self.remove(list_key, source_object_key)

        created_count = bulk_response.get("created_count", 0) or 0
        updated_count = bulk_response.get("updated_count", 0) or 0
        recipient_list = dict(bulk_response.get("recipient_list") or {})
        recipient_list["active_member_count"] = len(active_keys) - len(stale_keys)

        return {
            **bulk_response,
            "recipient_list": recipient_list,
            "created_count": created_count,
            "updated_count": updated_count,
            "upsert_count": len(payload.get("members") or []),
            "removed_count": len(stale_keys),
        }


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
        return self.request(
            DatamailerRequestData(
                method="POST",
                path="/api/transient-recipient-lists/transactional-send",
                json=payload,
            )
        )
