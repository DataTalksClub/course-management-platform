from django.core.exceptions import ValidationError
from django.http import JsonResponse

from api.safety import (
    ensure_no_related_records_for_delete,
    error_response,
)
from api.utils import parse_json_body
from courses.models.project import ReviewCriteria, ReviewCriteriaTypes
from courses.validators.criteria_validators import (
    validate_review_criteria_options,
)

from .review_criteria_serializers import review_criteria_to_dict

REVIEW_CRITERIA_TYPES = {
    ReviewCriteriaTypes.RADIO_BUTTONS.value,
    ReviewCriteriaTypes.CHECKBOXES.value,
}

REVIEW_CRITERIA_PATCH_FIELDS = {
    "description",
    "review_criteria_type",
    "options",
}

# Options and type shape how recorded scores are interpreted, so they are
# immutable once scores exist. The description stays editable.
SCORED_IMMUTABLE_FIELDS = {
    "review_criteria_type",
    "options",
}


def validate_criteria_type(value):
    if value not in REVIEW_CRITERIA_TYPES:
        valid_types = sorted(REVIEW_CRITERIA_TYPES)
        return (
            f"Invalid review_criteria_type. Must be one of: {valid_types}"
        )
    return None


def validate_criteria_options(options):
    try:
        validate_review_criteria_options(options)
    except ValidationError as exc:
        return "; ".join(exc.messages)
    return None


def validate_criteria_payload(data):
    description = data.get("description")
    if not description or not str(description).strip():
        return "description is required"

    criteria_type = data.get(
        "review_criteria_type",
        ReviewCriteriaTypes.RADIO_BUTTONS.value,
    )
    type_error = validate_criteria_type(criteria_type)
    if type_error:
        return type_error

    options = data.get("options")
    if options is None:
        return "options is required"
    return validate_criteria_options(options)


def create_review_criteria(course, criteria_data):
    error = validate_criteria_payload(criteria_data)
    if error:
        return None, error

    criteria = ReviewCriteria.objects.create(
        course=course,
        description=criteria_data["description"],
        review_criteria_type=criteria_data.get(
            "review_criteria_type",
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        ),
        options=criteria_data["options"],
    )

    criteria_record = review_criteria_to_dict(criteria)
    return criteria_record, None


def review_criteria_create_items(data):
    if isinstance(data, list):
        return data
    return [data]


def review_criteria_create_error(item, error):
    description = item.get("description", "unknown")
    return {"description": description, "error": error}


def review_criteria_create_response(course, data):
    created = []
    errors = []

    criteria_items = review_criteria_create_items(data)
    for item in criteria_items:
        if not isinstance(item, dict):
            errors.append({"description": "unknown", "error": "item must be an object"})
            continue
        criteria_record, error = create_review_criteria(course, item)
        if error:
            criteria_error = review_criteria_create_error(item, error)
            errors.append(criteria_error)
        else:
            created.append(criteria_record)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    if created:
        status = 201
    else:
        status = 400
    response = JsonResponse(result, status=status)
    return response


def review_criteria_delete_response(criteria):
    score_records = criteria.projectevaluationscore_set.all()
    error_response_result = ensure_no_related_records_for_delete(
        score_records, "scores", "criteria"
    )
    if error_response_result:
        return error_response_result

    criteria.delete()
    payload = {"deleted": True}
    response = JsonResponse(payload)
    return response


def review_criteria_invalid_field_response(field):
    details = {"field": field}
    return error_response(
        f"Cannot update field: {field}",
        "invalid_field",
        details=details,
    )


def review_criteria_scored_immutable_response(field):
    details = {"field": field}
    return error_response(
        f"Cannot update field: {field} has recorded scores",
        "criteria_has_scores",
        details=details,
    )


def apply_review_criteria_patch(criteria, data):
    has_scores = criteria.projectevaluationscore_set.exists()
    for field, value in data.items():
        if field not in REVIEW_CRITERIA_PATCH_FIELDS:
            return review_criteria_invalid_field_response(field)
        if has_scores and field in SCORED_IMMUTABLE_FIELDS:
            return review_criteria_scored_immutable_response(field)
        if field == "description" and (
            not value or not str(value).strip()
        ):
            return error_response(
                "description cannot be empty",
                "invalid_field",
                details={"field": field},
            )
        if field == "review_criteria_type":
            type_error = validate_criteria_type(value)
            if type_error:
                return error_response(
                    type_error,
                    "invalid_field",
                    details={"field": field},
                )
        if field == "options":
            options_error = validate_criteria_options(value)
            if options_error:
                return error_response(
                    options_error,
                    "invalid_field",
                    details={"field": field},
                )
        setattr(criteria, field, value)

    return None


def review_criteria_patch_response(criteria, request):
    data, err = parse_json_body(request)
    if err:
        return err

    error = apply_review_criteria_patch(criteria, data)
    if error:
        return error

    criteria.save()
    criteria_record = review_criteria_to_dict(criteria)
    response = JsonResponse(criteria_record)
    return response
