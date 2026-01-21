from django.core.exceptions import ValidationError


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
    if not isinstance(value, list):
        raise ValidationError(
            "Options must be a list of dictionaries, not %(type)s. "
            "Expected format: [{'criteria': 'text', 'score': 0}, ...]",
            params={'type': type(value).__name__},
        )
    
    if len(value) == 0:
        raise ValidationError("Options list cannot be empty.")
    
    for idx, option in enumerate(value):
        if not isinstance(option, dict):
            raise ValidationError(
                f"Option at index {idx} must be a dictionary, not {type(option).__name__}."
            )
        
        # Check for required keys
        if "criteria" not in option:
            raise ValidationError(
                f"Option at index {idx} is missing required key 'criteria'."
            )
        
        if "score" not in option:
            raise ValidationError(
                f"Option at index {idx} is missing required key 'score'."
            )
        
        # Validate types
        if not isinstance(option["criteria"], str):
            raise ValidationError(
                f"Option at index {idx}: 'criteria' must be a string, not {type(option['criteria']).__name__}."
            )
        
        if not isinstance(option["score"], int):
            raise ValidationError(
                f"Option at index {idx}: 'score' must be an integer, not {type(option['score']).__name__}."
            )
        
        # Validate criteria text is not empty
        if not option["criteria"].strip():
            raise ValidationError(
                f"Option at index {idx}: 'criteria' cannot be empty."
            )
