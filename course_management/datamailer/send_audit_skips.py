"""Per-recipient skip reasons for recipient-list send audits.

Relay returns ``skipped`` (message id, contact id, email, source object key,
reason) in recipient-list send responses, which are stored verbatim in
``DatamailerSendAudit.response_payload``. Audits recorded before Relay
returned that array can be resolved with a read-only Relay lookup.
"""

import logging
from datetime import timedelta

import requests

from accounts.models import CustomUser
from data.models import DatamailerSendAuditType

from .client import DatamailerClient, DatamailerConfig


logger = logging.getLogger(__name__)

LIST_SEND_TYPES = {
    DatamailerSendAuditType.RECIPIENT_LIST,
    DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
}
RELAY_SKIPPED_STATUS = "suppressed"
RELAY_RECONCILIATION_PAGE_SIZE = 1000
LOOKUP_WINDOW = timedelta(minutes=15)
MAX_LOOKUP_PAGES = 5
MAX_LOOKUP_MESSAGES = 50

# Relay's exact reason stays in "reason"; this is the coarse vocabulary.
REASON_CATEGORIES = {
    "category_unsubscribe": "opt_out",
    "global_unsubscribe": "opt_out",
    "hard_bounce": "suppressed",
    "complaint": "suppressed",
    "suppressed": "suppressed",
    "invalid_email": "invalid_email",
    "duplicate": "duplicate",
}

SOURCE_AUDIT = "audit"
SOURCE_RELAY_LOOKUP = "relay_lookup"
SOURCE_NOT_RECORDED = "not_recorded"
SOURCE_UNAVAILABLE = "unavailable"


def send_audit_skipped_recipients(audit, *, lookup=False):
    """Return {"skipped_recipients": [...], "skipped_recipients_source": ...}.

    ``lookup`` allows a read-only Relay query for audits that predate
    persisted skip details. List endpoints must not pass it.
    """
    persisted = (audit.response_payload or {}).get("skipped")
    if isinstance(persisted, list):
        return _result(persisted, SOURCE_AUDIT)
    if not audit.skipped_count or audit.send_type not in LIST_SEND_TYPES:
        return _result([], None)
    if not lookup:
        return _result([], SOURCE_NOT_RECORDED)

    config = DatamailerConfig.from_settings()
    if config is None:
        return _result([], SOURCE_UNAVAILABLE)
    try:
        items = _relay_skipped_items(DatamailerClient(config), audit)
    except requests.RequestException:
        logger.warning(
            "Relay skip lookup failed for send audit id=%s", audit.pk
        )
        return _result([], SOURCE_UNAVAILABLE)
    return _result(items, SOURCE_RELAY_LOOKUP)


def _result(items, source):
    return {
        "skipped_recipients": _with_user_ids(items),
        "skipped_recipients_source": source,
    }


def _relay_skipped_items(client, audit):
    prefix = f"{audit.idempotency_key}:"
    since = (audit.occurred_at - LOOKUP_WINDOW).isoformat()
    source_keys = {}
    for _ in range(MAX_LOOKUP_PAGES):
        page = client.transactional.transactional_messages_since(since) or {}
        messages = page.get("messages") or []
        for message in messages:
            reference = message.get("client_reference") or ""
            if (
                reference.startswith(prefix)
                and message.get("status") == RELAY_SKIPPED_STATUS
            ):
                source_keys[int(message["id"])] = reference[len(prefix):]
        if len(source_keys) >= audit.skipped_count:
            break
        if len(messages) < RELAY_RECONCILIATION_PAGE_SIZE:
            break
        next_since = messages[-1].get("updated_at")
        if not next_since or next_since == since:
            break
        since = next_since

    items = []
    for message_id in sorted(source_keys)[:MAX_LOOKUP_MESSAGES]:
        status = client.transactional.transactional_message_status(
            message_id
        ) or {}
        message = status.get("message") or {}
        items.append(
            {
                "message_id": message_id,
                "contact_id": message.get("contact_id"),
                "email": message.get("email", ""),
                "source_object_key": source_keys[message_id],
                "reason": message.get("last_error") or RELAY_SKIPPED_STATUS,
            }
        )
    return items


def _user_id_from_source_key(source_object_key):
    kind, _, value = (source_object_key or "").partition(":")
    if kind == "user" and value.isdigit():
        return int(value)
    return None


def _with_user_ids(items):
    emails = {
        (item.get("email") or "").strip().lower()
        for item in items
        if not _user_id_from_source_key(item.get("source_object_key"))
    }
    emails.discard("")
    user_ids_by_email = {}
    if emails:
        for user_id, email in CustomUser.objects.filter(
            email__in=emails
        ).values_list("id", "email"):
            user_ids_by_email[email.lower()] = user_id
        missing = emails - set(user_ids_by_email)
        for email in missing:
            user = CustomUser.objects.filter(email__iexact=email).first()
            if user is not None:
                user_ids_by_email[email] = user.pk

    result = []
    for item in items:
        email = (item.get("email") or "").strip().lower()
        source_object_key = item.get("source_object_key") or ""
        user_id = _user_id_from_source_key(source_object_key)
        if user_id is None:
            user_id = user_ids_by_email.get(email)
        reason = item.get("reason") or ""
        result.append(
            {
                "user_id": user_id,
                "email": email,
                "reason": reason,
                "reason_category": REASON_CATEGORIES.get(reason, "other"),
                "source_object_key": source_object_key,
                "relay_message_id": item.get("message_id"),
                "relay_contact_id": item.get("contact_id"),
            }
        )
    return result
