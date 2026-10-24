from dataclasses import dataclass
import hashlib
from typing import Any

from django.utils.dateformat import format as format_date

from course_management import email_templates

from ..client import DatamailerConfig
from ..preference_categories import EMAIL_PREFERENCE_CATEGORIES
from .registration_common import registration_email
from .urls import public_route_url


@dataclass(frozen=True)
class RegistrationConfirmationPayloadData:
    config: DatamailerConfig
    registration: object
    campaign: object
    course: object
    urls: dict[str, str]
    email: str


def registration_confirmation_urls(campaign, course, token="") -> dict[str, str]:
    registration_kwargs = {"campaign_slug": campaign.slug}
    registration_url = public_route_url(
        "registration_campaign",
        registration_kwargs,
    )
    course_url = ""
    if course is not None:
        course_kwargs = {"course_slug": course.slug}
        course_url = public_route_url("course", course_kwargs)
    profile_url = public_route_url("account_settings")
    confirmation_url = ""
    if token:
        confirmation_url = public_route_url(
            "registration_confirm",
            {"token": token},
        )
    return {
        "registration_url": registration_url,
        "course_url": course_url,
        "profile_url": profile_url,
        "confirmation_url": confirmation_url,
    }


def registration_confirmation_metadata(registration, campaign, course):
    course_slug = ""
    if course is not None:
        course_slug = course.slug
    return {
        "source": "course-management-platform",
        "event": "course_registration",
        "registration_id": registration.pk,
        "campaign_slug": campaign.slug,
        "course_slug": course_slug,
        "preference_key": "email_course_updates",
        "cmp_preference_key": "email_course_updates",
    }


def registration_confirmation_course_context(course):
    context = {
        "course_title": "",
        "course_slug": "",
        "course_start_date": "",
    }
    if course is not None:
        context["course_title"] = course.title
        context["course_slug"] = course.slug
        if course.start_date:
            context["course_start_date"] = format_date(
                course.start_date,
                "F j, Y",
            )
    return context


def registration_confirmation_context(registration, campaign, course, urls):
    profile_url = urls["profile_url"]
    course_context = registration_confirmation_course_context(course)
    context = {
        "email_subject": f"Confirm your registration: {campaign.title}",
        "campaign_title": campaign.title,
        "campaign_slug": campaign.slug,
        "registration_id": registration.pk,
        "registration_url": urls["registration_url"],
        "course_url": urls["course_url"],
        "profile_url": profile_url,
        "confirmation_url": urls.get("confirmation_url", ""),
        "intro_text": (
            f"Thanks for registering for {campaign.title}! "
            "Please click the confirmation link to complete "
            "your registration."
        ),
        "next_steps_text": (
            "Closer to the start, we will send you another email with "
            "more information about the course."
        ),
        "notification_category": "course-related emails",
        "notification_footer": (
            "You are receiving this because course-related emails are "
            "enabled."
        ),
        "notification_footer_text": (
            "If you don't want to receive course-related emails, turn "
            f"them off in your profile: {profile_url}"
        ),
    }
    context.update(course_context)
    return context


def registration_confirmation_payload(registration) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = registration_email(registration)
    if not email:
        return None

    campaign = registration.campaign
    course = registration.course
    token = registration.email_confirmation_token or ""
    urls = registration_confirmation_urls(campaign, course, token=token)
    payload_data = RegistrationConfirmationPayloadData(
        config=config,
        registration=registration,
        campaign=campaign,
        course=course,
        urls=urls,
        email=email,
    )
    return registration_confirmation_payload_from_data(payload_data)


def registration_confirmation_delivery_fields(
    data: RegistrationConfirmationPayloadData,
) -> dict[str, Any]:
    category = EMAIL_PREFERENCE_CATEGORIES["email_course_updates"]
    token = data.registration.email_confirmation_token or ""
    idempotency_key = f"registration-confirmation:{data.registration.pk}"
    if token:
        generation = hashlib.sha256(token.encode()).hexdigest()[:24]
        idempotency_key += f":{generation}"
    return {
        "audience": data.config.audience,
        "client": data.config.client,
        "email": data.email,
        "template_key": email_templates.REGISTRATION_CONFIRMATION,
        "category_tag": category["tag"],
        "idempotency_key": idempotency_key,
    }


def registration_confirmation_payload_from_data(
    data: RegistrationConfirmationPayloadData,
) -> dict[str, Any]:
    context = registration_confirmation_context(
        data.registration,
        data.campaign,
        data.course,
        data.urls,
    )
    metadata = registration_confirmation_metadata(
        data.registration,
        data.campaign,
        data.course,
    )
    payload = registration_confirmation_delivery_fields(data)
    payload["context"] = context
    payload["metadata"] = metadata
    return payload
