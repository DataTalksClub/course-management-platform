from typing import Any

from ..client import DatamailerConfig, public_url
from ..keys import course_graduates_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    normalized_email,
    recipient_list_member_payload,
    recipient_list_send_member_payload,
)
from .bulk import bulk_recipient_list_payload


def course_graduate_recipient_list_payload(
    enrollment,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    member_data = _course_graduate_member_data(enrollment)
    if member_data is None:
        return None

    course = enrollment.course
    source_object_key, member_payload = member_data
    member = recipient_list_send_member_payload(
        source_object_key,
        member_payload,
    )
    members = [member]
    payload = bulk_recipient_list_payload(
        config,
        member_payload["list"],
        members,
    )
    list_key = course_graduates_list_key(course)
    return list_key, payload


def _course_graduate_certificate_url(enrollment) -> str:
    certificate_url = enrollment.certificate_url or ""
    stripped_certificate_url = certificate_url.strip()
    return stripped_certificate_url


def _course_graduate_source_object_key(enrollment) -> str:
    return f"enrollment:{enrollment.pk}"


def _course_graduate_member_data(enrollment):
    email = normalized_email(enrollment.student.email)
    certificate_url = _course_graduate_certificate_url(enrollment)
    if not email or not certificate_url:
        return None

    source_object_key = _course_graduate_source_object_key(enrollment)
    metadata = _course_graduate_metadata(enrollment, certificate_url)
    payload_data = RecipientListMemberPayloadData(
        list_type="custom",
        list_name=f"{enrollment.course.title} graduates",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    member_payload = recipient_list_member_payload(payload_data)
    if member_payload is None:
        return None
    return source_object_key, member_payload


def _course_graduate_metadata(enrollment, certificate_url):
    course = enrollment.course
    public_certificate_url = public_url(certificate_url)
    return {
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
        "course_slug": course.slug,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
        "certificate_url": public_certificate_url,
        "outcome": "course_graduated",
    }


def course_graduate_recipient_list_member_payload(
    enrollment,
) -> RecipientListMemberPayload | None:
    list_payload = course_graduate_recipient_list_payload(enrollment)
    if list_payload is None:
        return None

    list_key, payload = list_payload
    member = payload["members"][0]
    member_payload = {
        "audience": payload["audience"],
        "client": payload["client"],
        "list": payload["list"],
        "member": {
            "email": member["email"],
            "status": member["status"],
            "metadata": member["metadata"],
        },
    }
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=member["source_object_key"],
        payload=member_payload,
    )
