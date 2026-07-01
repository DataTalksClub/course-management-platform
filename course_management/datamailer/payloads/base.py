from dataclasses import dataclass
from typing import Any

from ..client import DatamailerConfig
from ..keys import (
    contact_tags_for_course,
    course_enrolled_list_key,
    course_family_slug,
)


@dataclass(frozen=True)
class RecipientListMemberPayloadData:
    list_type: str
    list_name: str
    email: str
    source_object_key: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RecipientListMemberPayload:
    list_key: str
    source_object_key: str
    payload: dict[str, Any]


def contact_base_custom_fields(user) -> dict[str, str]:
    return {
        "course_platform_user_id": str(user.pk),
        "username": user.username or "",
    }


def contact_course_custom_fields(course) -> dict[str, str]:
    return {
        "course_slug": course.slug,
        "course_family_slug": course_family_slug(course),
        "course_cohort_slug": course.slug,
        "course_title": course.title,
    }


def contact_payload_tags_and_fields(user, course):
    tags = []
    custom_fields = contact_base_custom_fields(user)

    if course is not None:
        course_tags = contact_tags_for_course(course)
        tags.extend(course_tags)

        course_custom_fields = contact_course_custom_fields(course)
        custom_fields.update(course_custom_fields)

    return tags, custom_fields


def contact_payload_for_user(
    user, course=None
) -> dict[str, Any] | None:
    email_value = user.email or ""
    stripped_email = email_value.strip()
    email = stripped_email.lower()
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags, custom_fields = contact_payload_tags_and_fields(user, course)

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "status": "subscribed",
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": tags,
        "custom_fields": custom_fields,
    }


def recipient_list_member_payload(data) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return {
        "audience": config.audience,
        "client": config.client,
        "list": {
            "type": data.list_type,
            "name": data.list_name,
            "metadata": data.metadata,
        },
        "member": {
            "email": data.email.strip().lower(),
            "status": "active",
            "metadata": data.metadata
            | {"source_object_key": data.source_object_key},
        },
    }

def removed_recipient_list_member_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "member": {
            **payload["member"],
            "status": "removed",
        },
    }

def enrollment_recipient_metadata(enrollment) -> dict[str, Any]:
    return {
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
        "course_slug": enrollment.course.slug,
        "display_name": enrollment.display_name,
    }


def enrollment_recipient_list_payload(
    enrollment,
) -> RecipientListMemberPayload | None:
    email_value = enrollment.student.email or ""
    stripped_email = email_value.strip()
    email = stripped_email.lower()
    if not email:
        return None

    course = enrollment.course
    list_key = course_enrolled_list_key(course)
    source_object_key = f"user:{enrollment.student_id}"
    payload_data = RecipientListMemberPayloadData(
        list_type="custom",
        list_name=f"{course.title} enrolled learners",
        email=email,
        source_object_key=source_object_key,
        metadata=enrollment_recipient_metadata(enrollment),
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )

def recipient_list_send_member_payload(
    source_object_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    member = payload["member"]
    return {
        "source_object_key": source_object_key,
        "email": member["email"],
        "status": member["status"],
        "metadata": member["metadata"],
    }
