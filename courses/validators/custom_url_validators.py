import requests
from django.core.exceptions import ValidationError

def validate_url_200(value):
    try:
        response = requests.get(value)
        if response.status_code != 200:
            raise ValidationError(f'The URL provided does not return a 200 status code. Status code: {response.status_code}')
    except requests.exceptions.RequestException as e:
        raise ValidationError(f'An error occurred while trying to validate the URL: {e}')
