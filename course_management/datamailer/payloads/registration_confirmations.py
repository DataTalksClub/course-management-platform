from dataclasses import dataclass
from typing import Any

from django.urls import reverse

from course_management import email_templates

from ..client import DatamailerConfig, public_url
from ..preferences import EMAIL_PREFERENCE_CATEGORIES
from .registration_common import registration_email


@dataclass(frozen=True)
class RegistrationConfirmationPayloadData:
    config: DatamailerConfig
    registration: object
    campaign: object
    course: object
    urls: dict[str, str]
    email: str


def registration_confirmation_urls(campaign, course) -> dict[str, str]:
    registration_path = reverse(
        "registration_campaign",
        kwargs={"campaign_slug": campaign.slug},
    )
    course_url = ""
    if course is not None:
        course_path = reverse("course", kwargs={"course_slug": course.slug})
        course_url = public_url(course_path)
    registration_url = public_url(registration_path)
    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)
    return {
        "registration_url": registration_url,
        "course_url": course_url,
        "profile_url": profile_url,
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
    }
    if course is not None:
        context["course_title"] = course.title
        context["course_slug"] = course.slug
    return context


def registration_confirmation_context(registration, campaign, course, urls):
    profile_url = urls["profile_url"]
    course_context = registration_confirmation_course_context(course)
    context = {
        "email_subject": f"Registration confirmed: {campaign.title}",
        "campaign_title": campaign.title,
        "campaign_slug": campaign.slug,
        "registration_id": registration.pk,
        "registration_url": urls["registration_url"],
        "course_url": urls["course_url"],
        "profile_url": profile_url,
        "intro_text": (
            f"Your registration for {campaign.title} is confirmed."
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
    urls = registration_confirmation_urls(campaign, course)
    payload_data = RegistrationConfirmationPayloadData(
        config=config,
        registration=registration,
        campaign=campaign,
        course=course,
        urls=urls,
        email=email,
    )
    return registration_confirmation_payload_from_data(payload_data)


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
    return {
        "audience": data.config.audience,
        "client": data.config.client,
        "email": data.email,
        "template_key": email_templates.REGISTRATION_CONFIRMATION,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "idempotency_key": (
            f"registration-confirmation:{data.registration.pk}"
        ),
        "context": context,
        "metadata": metadata,
    }
