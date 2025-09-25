import requests

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def get_error_message(status_code, url):
    if status_code != 404:
        return (
            f"The submitted link {url} does not "
            + "return a 200 status code. Status code: "
            + f"{status_code}."
        )

    # 404 status code
    if "github" in url.lower():
        return (
            f"The submitted GitHub link {url} does not "
            + "exist. Make sure the repository is public."
        )

    return f"The submitted link {url} does not exist."


def validate_url_200(
    url, get_method=None, code=None, params=None
):
    if get_method is None:
        get_method = requests.get
        
    try:
        response = get_method(url)
        status_code = response.status_code
        if status_code == 200:
            return
        error_message = get_error_message(status_code, url)
        raise ValidationError(error_message, code=code, params=params)
    except requests.exceptions.RequestException as e:
        raise ValidationError(
            f"An error occurred while trying to validate the URL: {e}",
            code=code,
            params=params,
        )


class Status200UrlValidator(URLValidator):
    def __call__(self, value):
        print(f"validating {value}")
        super().__call__(value)
        validate_url_200(value, code=self.code, params={"value": value})
