import json
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from courses.validators import validate_url_200

class ValidatingJSONField(models.JSONField):
    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        
        for link in value:
            # Validate each URL in the JSON array data
            try:
                validators.URLValidator()(link)
                validate_url_200(link)
            except ValidationError as e:
                raise ValidationError(e.message)