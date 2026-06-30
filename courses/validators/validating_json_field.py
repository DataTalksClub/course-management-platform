from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from courses.validators.custom_url_validators import validate_url_200


class ValidatingJSONField(models.JSONField):
    def validate(self, value, model_instance):
        super().validate(value, model_instance)

        url_validator = validators.URLValidator()
        for link in value:
            # Validate each URL in the JSON array data
            try:
                url_validator(link)
                validate_url_200(link)
            except ValidationError as e:
                raise ValidationError(e.message)
