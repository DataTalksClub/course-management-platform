from django.core.exceptions import ValidationError


def validate_options_is_list(value):
    if not isinstance(value, list):
        raise ValidationError(
            "Options must be a list of dictionaries, not %(type)s. "
            "Expected format: [{'criteria': 'text', 'score': 0}, ...]",
            params={'type': type(value).__name__},
        )

    if len(value) == 0:
        raise ValidationError("Options list cannot be empty.")


def validate_option_is_dict(option, idx):
    if not isinstance(option, dict):
        raise ValidationError(
            f"Option at index {idx} must be a dictionary, not {type(option).__name__}."
        )


def validate_option_keys(option, idx):
    if "criteria" not in option:
        raise ValidationError(
            f"Option at index {idx} is missing required key 'criteria'."
        )

    if "score" not in option:
        raise ValidationError(
            f"Option at index {idx} is missing required key 'score'."
        )


def validate_option_types(option, idx):
    if not isinstance(option["criteria"], str):
        raise ValidationError(
            f"Option at index {idx}: 'criteria' must be a string, not {type(option['criteria']).__name__}."
        )

    if not isinstance(option["score"], int):
        raise ValidationError(
            f"Option at index {idx}: 'score' must be an integer, not {type(option['score']).__name__}."
        )


def validate_option_content(option, idx):
    if not option["criteria"].strip():
        raise ValidationError(
            f"Option at index {idx}: 'criteria' cannot be empty."
        )


def validate_review_criteria_option(option, idx):
    validate_option_is_dict(option, idx)
    validate_option_keys(option, idx)
    validate_option_types(option, idx)
    validate_option_content(option, idx)


def validate_review_criteria_options(value):
    """
    Validates that the review criteria options JSON field has the correct structure.

    Expected structure:
    [
        {"criteria": "Poor", "score": 0},
        {"criteria": "Satisfactory", "score": 1},
        ...
    ]
    """
    validate_options_is_list(value)

    indexed_options = enumerate(value)
    for idx, option in indexed_options:
        validate_review_criteria_option(option, idx)
