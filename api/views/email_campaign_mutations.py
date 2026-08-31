from django.core.exceptions import ValidationError

from api.safety import error_response
from api.utils import parse_json_body
from courses.models.course import EmailCampaign


EMAIL_CAMPAIGN_FIELDS = {
    "subject",
    "preview_text",
    "body_markdown",
}


def clean_email_campaign_payload(request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    err = email_campaign_field_error(data)
    if err:
        return None, err

    return data, None


def created_email_campaign(registration_campaign, data):
    error = email_campaign_required_fields_error(data)
    if error:
        return None, error

    email_campaign = EmailCampaign(
        registration_campaign=registration_campaign, **data
    )
    error = save_email_campaign(email_campaign)
    if error:
        return None, error

    return email_campaign, None


def save_email_campaign(email_campaign):
    try:
        email_campaign.full_clean(exclude=["external_key"])
    except ValidationError as exc:
        return email_campaign_validation_error_response(exc)

    email_campaign.save()
    return None


def email_campaign_validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        details = exc.message_dict
    else:
        details = {"errors": exc.messages}
    return error_response(
        "Email campaign validation failed",
        "validation_error",
        details=details,
    )


def email_campaign_field_error(data):
    unknown_fields = set(data) - EMAIL_CAMPAIGN_FIELDS
    if not unknown_fields:
        return None

    field = sorted(unknown_fields)[0]
    return error_response(
        f"Cannot set field: {field}",
        "invalid_field",
        details={"field": field},
    )


def email_campaign_required_fields_error(data):
    if data.get("subject"):
        return None

    return error_response(
        "subject is required",
        "missing_required_fields",
    )
