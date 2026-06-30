from typing import Any

from data.models import DatamailerSendAuditType

from ..client import DatamailerConfig

def recipient_list_member_sync_payload(
    config: DatamailerConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "audience": config.audience,
        "client": config.client,
        "list": payload["list"],
        "members": payload["members"],
    }

def recipient_list_send_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    excluded_keys = {
        "list",
        "members",
        "member_sync",
        "remove_absent_members",
    }
    send_payload = {}
    for key, value in payload.items():
        if key not in excluded_keys:
            send_payload[key] = value
    return send_payload


def recipient_list_response_key(response: dict[str, Any]) -> str:
    recipient_list = response.get("recipient_list") or {}
    return recipient_list.get("key", "")


def transient_recipient_list_key(
    payload: dict[str, Any],
    response: dict[str, Any],
) -> str:
    transient_list = response.get("transient_recipient_list") or {}
    if transient_list.get("key"):
        return transient_list["key"]

    list_data = payload.get("list") or {}
    return list_data.get("key", "")


def datamailer_send_list_key(
    send_type: str,
    *,
    explicit_list_key: str,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> str:
    if explicit_list_key:
        return explicit_list_key
    if send_type == DatamailerSendAuditType.RECIPIENT_LIST:
        return recipient_list_response_key(response)
    if send_type == DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST:
        return transient_recipient_list_key(payload, response)
    return ""


def _response_count(response: dict[str, Any], key: str) -> int:
    return int(response.get(key) or 0)


def _transactional_send_counts(response: dict[str, Any]) -> dict[str, int]:
    idempotent_replay_count = int(bool(response.get("idempotent_replay")))
    message = response.get("message") or {}
    return {
        "intended_count": 1,
        "created_count": int(bool(response) and not idempotent_replay_count),
        "enqueued_count": int(bool(response.get("enqueued"))),
        "skipped_count": int(message.get("status") == "skipped"),
        "idempotent_replay_count": idempotent_replay_count,
    }


def _recipient_list_intended_count(response: dict[str, Any]) -> int:
    recipient_list = response.get("recipient_list") or {}
    return int(recipient_list.get("active_member_count") or 0)


def _active_payload_member_count(payload: dict[str, Any]) -> int:
    members = payload.get("members")
    if not isinstance(members, list):
        return 0
    count = 0
    for member in members:
        if member.get("status") != "removed":
            count += 1
    return count


def _transient_recipient_list_intended_count(
    payload: dict[str, Any],
    response: dict[str, Any],
) -> int:
    transient_list = response.get("transient_recipient_list") or {}
    response_count = int(transient_list.get("active_member_count") or 0)
    if response_count:
        return response_count
    return _active_payload_member_count(payload)


def _recipient_send_counts(
    intended_count: int,
    response: dict[str, Any],
) -> dict[str, int]:
    return {
        "intended_count": intended_count,
        "created_count": _response_count(response, "created_count"),
        "enqueued_count": _response_count(response, "enqueued_count"),
        "skipped_count": _response_count(response, "skipped_count"),
        "idempotent_replay_count": _response_count(
            response,
            "idempotent_replay_count",
        ),
    }


def datamailer_send_counts(
    send_type: str,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, int]:
    if send_type == DatamailerSendAuditType.TRANSACTIONAL:
        return _transactional_send_counts(response)

    intended_count = 0
    if send_type == DatamailerSendAuditType.RECIPIENT_LIST:
        intended_count = _recipient_list_intended_count(response)
    elif send_type == DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST:
        intended_count = _transient_recipient_list_intended_count(
            payload,
            response,
        )

    return _recipient_send_counts(intended_count, response)
