from django.core.exceptions import ValidationError

from api.safety import error_response
from api.utils import parse_json_body
from courses.models.course import Course, RegistrationCampaign


CAMPAIGN_FIELDS = {
    "slug",
    "title",
    "edition_label",
    "current_course",
    "is_active",
    "marketing_markdown",
    "meta_description",
    "hero_image_url",
    "video_url",
}


def clean_campaign_payload(request, *, action):
    data, err = parse_json_body(request)
    if err:
        return None, err

    err = campaign_field_error(data, action)
    if err:
        return None, err

    return normalize_campaign_data(data)


def created_campaign(data):
    error = campaign_required_fields_error(data)
    if error:
        return None, error

    campaign = RegistrationCampaign(**data)
    error = save_campaign(campaign)
    if error:
        return None, error

    return campaign, None


def apply_campaign_patch(campaign, data):
    for field, value in data.items():
        setattr(campaign, field, value)

    error = save_campaign(campaign)
    if error:
        return error

    return None


def normalize_campaign_data(data):
    result = data.copy()

    if "current_course" in result:
        slug = result.pop("current_course")
        if slug in ("", None):
            result["current_course"] = None
        else:
            try:
                result["current_course"] = Course.objects.get(slug=slug)
            except Course.DoesNotExist:
                return None, error_response(
                    f"Course with slug '{slug}' does not exist",
                    "course_not_found",
                    details={"current_course": slug},
                )

    return result, None


def save_campaign(campaign):
    try:
        campaign.full_clean()
    except ValidationError as exc:
        return validation_error_response(exc)

    campaign.save()
    return None


def validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        details = exc.message_dict
    else:
        details = {"errors": exc.messages}
    return error_response(
        "Registration campaign validation failed",
        "validation_error",
        details=details,
    )


def invalid_campaign_field_response(field, action):
    return error_response(
        f"Cannot {action} field: {field}",
        "invalid_field",
        details={"field": field},
    )


def campaign_field_error(data, action):
    unknown_fields = set(data) - CAMPAIGN_FIELDS
    if not unknown_fields:
        return None

    field = sorted(unknown_fields)[0]
    return invalid_campaign_field_response(field, action)


def campaign_required_fields_error(data):
    title = data.get("title")
    slug = data.get("slug")
    if title and slug:
        return None

    error = error_response(
        "title and slug are required",
        "missing_required_fields",
    )
    return error
