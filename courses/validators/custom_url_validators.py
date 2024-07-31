import requests
from django.core.exceptions import ValidationError


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


def validate_url_200(url, get_method=requests.get):
    try:
        response = get_method(url)
        status_code = response.status_code
        if status_code == 200:
            return
        error_message = get_error_message(status_code, url)
        raise ValidationError(error_message)
    except requests.exceptions.RequestException as e:
        raise ValidationError(
            f"An error occurred while trying to validate the URL: {e}"
        )
