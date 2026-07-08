from typing import Any

from ..keys import registration_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
)
from .registration_common import registration_email


def registration_recipient_list_payload(
    registration,
) -> RecipientListMemberPayload | None:
    email = registration_email(registration)
    if not email:
        return None

    list_key = registration_list_key(registration)
    source_object_key = f"registration:{registration.pk}"
    list_name = registration_recipient_list_name(registration)
    metadata = registration_recipient_metadata(registration)
    payload_data = RecipientListMemberPayloadData(
        list_type="registrants",
        list_name=list_name,
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )


def registration_recipient_list_name(registration) -> str:
    course = registration.course
    if course is not None:
        title = course.title
    else:
        title = registration.campaign.title
    return f"{title} registrants"


def registration_recipient_metadata(registration) -> dict[str, Any]:
    course = registration.course
    course_slug = ""
    if course is not None:
        course_slug = course.slug
    registered_at = ""
    if registration.created_at:
        registered_at = registration.created_at.isoformat()
    return {
        "registration_id": registration.pk,
        "campaign_slug": registration.campaign.slug,
        "course_slug": course_slug,
        "user_id": registration.user_id,
        "registered_at": registered_at,
        "company_name": registration.company_name,
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
    }
