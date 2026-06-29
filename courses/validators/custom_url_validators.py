from typing import Optional
from urllib.parse import urlparse

import requests

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

FAQ_CONTRIBUTION_FIELD = "faq_contribution_url"
FAQ_URL_FORMAT_ERROR = (
    "FAQ contribution must be a valid HTTPS GitHub issue "
    "or pull request URL."
)
FAQ_URL_REPOSITORY_ERROR = (
    "FAQ contribution must be a DataTalksClub/faq issue "
    "or pull request URL, for example "
    "https://github.com/DataTalksClub/faq/issues/281."
)
FAQ_URL_VALIDATOR = URLValidator(schemes=["https"])


def clean_faq_contribution_url(url: Optional[str]) -> str:
    url = (url or "").strip()
    if not url:
        return ""

    _validate_faq_contribution_url_format(url)
    if not _is_faq_issue_or_pull_request(url):
        raise _faq_contribution_url_error(FAQ_URL_REPOSITORY_ERROR)

    return url


def _validate_faq_contribution_url_format(url: str) -> None:
    try:
        FAQ_URL_VALIDATOR(url)
    except ValidationError:
        raise _faq_contribution_url_error(FAQ_URL_FORMAT_ERROR)


def _is_faq_issue_or_pull_request(url: str) -> bool:
    parsed = urlparse(url)
    path_parts = _url_path_parts(parsed.path)
    return _is_faq_github_host(parsed) and _is_faq_issue_or_pull_path(
        path_parts
    )


def _url_path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _is_faq_github_host(parsed_url) -> bool:
    return parsed_url.hostname == "github.com"


def _is_faq_issue_or_pull_path(path_parts: list[str]) -> bool:
    return (
        len(path_parts) == 4
        and path_parts[0].lower() == "datatalksclub"
        and path_parts[1].lower() == "faq"
        and path_parts[2].lower() in {"issues", "pull"}
        and path_parts[3].isdigit()
    )


def _faq_contribution_url_error(message: str) -> ValidationError:
    return ValidationError({FAQ_CONTRIBUTION_FIELD: message})


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


# Cap how long we wait on the remote server so a slow or hanging URL
# cannot tie up a worker process indefinitely.
URL_VALIDATION_TIMEOUT = 3


def validate_url_200(
    url, get_method=None, code=None, params=None
):
    if get_method is None:
        get_method = requests.head

    try:
        response = get_method(url, timeout=URL_VALIDATION_TIMEOUT)

        if response.status_code in [403, 405, 501]:
            response = requests.get(url, timeout=URL_VALIDATION_TIMEOUT)

        status_code = response.status_code

        if status_code == 200:
            return

        error_message = get_error_message(status_code, url)
        raise ValidationError(error_message, code=code, params=params)
    except ValidationError:
        raise
    except Exception as e:
        # Not just requests.exceptions.RequestException: malformed-but-
        # valid-looking URLs can raise UnicodeError / LocationParseError,
        # which would otherwise escape as an uncaught 500.
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
