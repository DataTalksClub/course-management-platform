from typing import Any

from django.urls import reverse

from course_management import email_templates

from ..client import DatamailerConfig, public_url
from .base import normalized_email


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
    email = normalized_email(enrollment.student.email)
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
