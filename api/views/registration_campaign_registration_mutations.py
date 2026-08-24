from functools import partial

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction

from api.safety import error_response
from api.utils import parse_json_body
from course_management.datamailer.sync.memberships import (
    sync_registration_to_datamailer,
)
from courses.models.course import CourseRegistration
from courses.registration import region_for_country
from courses.views.registration_form import normalized_registration_email

from .registration_campaign_serializers import registration_to_dict

REGISTRATION_FIELDS = {
    "email",
    "name",
    "company_name",
    "country",
    "role",
    "comment",
    "accepted_newsletter",
}
VALID_ROLES = {choice for choice, _label in CourseRegistration.Role.choices}
EMAIL_VALIDATOR = EmailValidator()


def bulk_create_registrations_payload(campaign, request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    items, err = registration_items(data)
    if err:
        return None, err

    results = [create_or_skip_registration(campaign, item) for item in items]
    payload = {**results_summary(results), "results": results}
    return payload, None


def registration_items(data):
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("registrations"), list):
        items = data["registrations"]
    else:
        error = error_response(
            'Body must be a list of registrations, or '
            '{"registrations": [...]}',
            "invalid_body",
        )
        return None, error

    if not items:
        error = error_response("No registrations provided", "empty_body")
        return None, error

    return items, None


def create_or_skip_registration(campaign, item):
    if not isinstance(item, dict):
        return {"status": "error", "errors": {"item": "must be an object"}}

    raw_email = item.get("email") or ""
    field_error = registration_field_error(item, raw_email)
    if field_error:
        return {"email": raw_email, "status": "error", "errors": field_error}

    email_normalized = normalized_registration_email(raw_email)
    existing = CourseRegistration.objects.filter(
        campaign=campaign,
        email_normalized=email_normalized,
    ).first()
    if existing:
        return {
            "email": email_normalized,
            "status": "skipped",
            "id": existing.id,
            "reason": "already registered",
        }

    registration = built_registration(campaign, item, email_normalized)
    registration.save()
    sync_callback = partial(sync_registration_to_datamailer, registration)
    transaction.on_commit(sync_callback)

    result = registration_to_dict(registration)
    result["status"] = "created"
    return result


def registration_field_error(item, raw_email):
    unknown_fields = set(item) - REGISTRATION_FIELDS
    if unknown_fields:
        field = sorted(unknown_fields)[0]
        return {"field": f"Unknown field: {field}"}

    email = raw_email.strip()
    if not email:
        return {"email": "This field is required"}
    try:
        EMAIL_VALIDATOR(email)
    except ValidationError:
        return {"email": "Enter a valid email address"}

    role = item.get("role") or ""
    if role and role not in VALID_ROLES:
        return {"role": f"Invalid role: {role}"}

    country = item.get("country") or ""
    if country and not region_for_country(country):
        return {"country": "Select a valid country"}

    return None


def built_registration(campaign, item, email_normalized):
    country = item.get("country") or ""
    return CourseRegistration(
        campaign=campaign,
        course=campaign.current_course,
        email=email_normalized,
        name=item.get("name") or "",
        company_name=item.get("company_name") or "",
        country=country,
        region=region_for_country(country),
        role=item.get("role") or "",
        comment=item.get("comment") or "",
        accepted_newsletter=bool(item.get("accepted_newsletter", False)),
    )


def results_summary(results):
    created = 0
    skipped = 0
    errors = 0
    for result in results:
        if result["status"] == "created":
            created += 1
        elif result["status"] == "skipped":
            skipped += 1
        else:
            errors += 1
    return {"created": created, "skipped": skipped, "errors": errors}
