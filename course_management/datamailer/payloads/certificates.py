from typing import Any

from django.urls import reverse

from course_management import email_templates

from ..client import DatamailerConfig, public_url
from ..keys import course_graduates_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
    recipient_list_send_member_payload,
)
from .bulk import bulk_recipient_list_payload

def _certificate_availability_urls(enrollment):
    course = enrollment.course
    certificate_path = enrollment.certificate_url.strip()
    certificate_url = public_url(certificate_path)
    course_path = reverse("course", kwargs={"course_slug": course.slug})
    course_url = public_url(course_path)
    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)
    return {
        "course_url": course_url,
        "certificate_url": certificate_url,
        "profile_url": profile_url,
    }


def _certificate_availability_context(enrollment, urls):
    course = enrollment.course
    certificate_url = urls["certificate_url"]
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "certificate_url": certificate_url,
        "course_url": urls["course_url"],
        "profile_url": urls["profile_url"],
        "email_subject": f"Certificate available: {course.title}",
        "email_preview": (
            "Your course certificate is available to download."
        ),
        "intro_text": (
            f"Congratulations - your certificate for {course.title} "
            "is available."
        ),
        "download_text": (
            f"You can download your certificate here: {certificate_url}"
        ),
        "notification_category": "course-related emails",
        "notification_footer": (
            "You are receiving this because general course-related "
            "emails are enabled."
        ),
    }


def _certificate_availability_metadata(enrollment):
    return {
        "source": "course-management-platform",
        "event": "certificate_availability",
        "preference_key": "email_course_updates",
        "cmp_preference_key": "email_course_updates",
        "course_slug": enrollment.course.slug,
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
    }


def _certificate_availability_recipient(enrollment) -> str | None:
    email_value = enrollment.student.email or ""
    stripped_email = email_value.strip()
    email = stripped_email.lower()
    certificate_url = enrollment.certificate_url or ""
    stripped_certificate_url = certificate_url.strip()
    if not email or not stripped_certificate_url:
        return None

    return email


def _certificate_availability_base_payload(
    config: DatamailerConfig,
    enrollment,
    email: str,
) -> dict[str, Any]:
    urls = _certificate_availability_urls(enrollment)
    context = _certificate_availability_context(enrollment, urls)
    metadata = _certificate_availability_metadata(enrollment)
    return {
        "audience": config.audience,
        "client": config.client,
        "email": email,
        "template_key": (
            email_templates.CERTIFICATE_AVAILABILITY_NOTIFICATION
        ),
        "category_tag": "course-updates",
        "idempotency_key": f"certificate-available:{enrollment.pk}",
        "context": context,
        "metadata": metadata,
    }


def _add_from_email_if_configured(payload, config):
    if config.from_email:
        payload["from_email"] = config.from_email
    return payload


def certificate_availability_notification_payload(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = _certificate_availability_recipient(enrollment)
    if email is None:
        return None

    payload = _certificate_availability_base_payload(
        config, enrollment, email
    )
    return _add_from_email_if_configured(payload, config)


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


def _course_graduate_email(enrollment) -> str:
    email = enrollment.student.email or ""
    stripped_email = email.strip()
    normalized_email = stripped_email.lower()
    return normalized_email


def _course_graduate_certificate_url(enrollment) -> str:
    certificate_url = enrollment.certificate_url or ""
    stripped_certificate_url = certificate_url.strip()
    return stripped_certificate_url


def _course_graduate_source_object_key(enrollment) -> str:
    return f"enrollment:{enrollment.pk}"


def _course_graduate_member_data(enrollment):
    email = _course_graduate_email(enrollment)
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
