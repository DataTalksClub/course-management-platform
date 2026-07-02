from collections import OrderedDict

from django.core.management.base import CommandError

from course_management.datamailer.payloads.base import (
    RecipientListMemberPayload,
)
from course_management.datamailer.recipient_list_sources import (
    RECIPIENT_LIST_SOURCES,
    RecipientListFilters,
)


def add_member_to_batches(batches, item):
    payload = item.payload
    batch = batches.setdefault(
        item.list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    member = {
        "source_object_key": item.source_object_key,
        "email": payload["member"]["email"],
        "status": payload["member"]["status"],
        "metadata": payload["member"]["metadata"],
    }
    batch["members"].append(member)


def add_payload_members_to_batches(batches, list_key, payload):
    batch = batches.setdefault(
        list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    batch["members"].extend(payload["members"])


def build_batches(
    kind, *, course_slug="", homework_slug="", project_slug=""
):
    source = RECIPIENT_LIST_SOURCES.get(kind)
    if source is None:
        raise CommandError(f"Unknown recipient list kind: {kind}")

    queryset_for, payload_for = source
    batches = OrderedDict()
    filters = RecipientListFilters(
        course_slug=course_slug,
        homework_slug=homework_slug,
        project_slug=project_slug,
    )
    objects = queryset_for(filters)
    for obj in objects:
        item = payload_for(obj)
        if item is None:
            continue
        if isinstance(item, RecipientListMemberPayload):
            add_member_to_batches(batches, item)
            continue
        list_key, payload = item
        add_payload_members_to_batches(batches, list_key, payload)
    return batches
