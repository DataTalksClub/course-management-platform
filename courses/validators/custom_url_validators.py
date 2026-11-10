import ipaddress
import socket
from time import monotonic
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


def clean_faq_contribution_url(url: str | None) -> str:
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
    path_parts = []
    raw_parts = path.split("/")
    for part in raw_parts:
        if part:
            path_parts.append(part)
    return path_parts


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


GITHUB_REPOSITORY_ERROR = (
    "The project link must be a GitHub repository URL, for example "
    "https://github.com/owner/repository."
)
GITHUB_HOSTS = {"github.com", "www.github.com"}


def is_github_repository_url(url: str | None) -> bool:
    try:
        parsed = urlparse((url or "").strip())
        hostname = parsed.hostname
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False
    if hostname not in GITHUB_HOSTS:
        return False
    return len(_url_path_parts(parsed.path)) >= 2


def validate_github_repository_url(url):
    if not is_github_repository_url(url):
        raise ValidationError(
            GITHUB_REPOSITORY_ERROR, code="invalid_github_repository"
        )


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
URL_VALIDATION_ERRORS = (
    requests.RequestException,
    OSError,
    UnicodeError,
    ValueError,
)
URL_PUBLIC_ADDRESS_ERROR = (
    "The submitted link must use a public HTTP or HTTPS address "
    "on port 80 or 443."
)
URL_REACHABILITY_ERROR = (
    "The submitted link could not be reached. Confirm it is a public URL "
    "and try again."
)


def _public_url_address(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValidationError(URL_PUBLIC_ADDRESS_ERROR)

    if (
        parsed.scheme not in ("http", "https")
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValidationError(URL_PUBLIC_ADDRESS_ERROR)

    expected_port = 80 if parsed.scheme == "http" else 443
    if port not in (None, expected_port):
        raise ValidationError(URL_PUBLIC_ADDRESS_ERROR)

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        resolved = socket.getaddrinfo(
            hostname,
            expected_port,
            type=socket.SOCK_STREAM,
        )
        addresses = [
            ipaddress.ip_address(result[4][0].split("%", 1)[0])
            for result in resolved
        ]

    if not addresses or any(not address.is_global for address in addresses):
        raise ValidationError(URL_PUBLIC_ADDRESS_ERROR)


def _url_validation_method(get_method):
    if get_method:
        return get_method
    return requests.head


def _should_retry_with_get(status_code):
    return status_code in [403, 405, 501]


def _validated_url_response(url, get_method):
    _public_url_address(url)
    deadline = monotonic() + URL_VALIDATION_TIMEOUT
    response = get_method(
        url,
        timeout=_remaining_url_timeout(deadline),
        allow_redirects=False,
    )
    if _should_retry_with_get(response.status_code):
        close_response = getattr(response, "close", None)
        if close_response:
            close_response()
        return requests.get(
            url,
            timeout=_remaining_url_timeout(deadline),
            allow_redirects=False,
            stream=True,
        )

    return response


def _remaining_url_timeout(deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise requests.Timeout("URL validation exceeded its time budget")
    # Requests applies connect and read timeouts independently. Split the
    # remaining budget so their combined maximum stays within our deadline.
    return (remaining / 2, remaining / 2)


def _raise_url_status_error(status_code, url, code, params):
    error_message = get_error_message(status_code, url)
    raise ValidationError(error_message, code=code, params=params)


def validate_url_200(url, get_method=None, code=None, params=None):
    get_method = _url_validation_method(get_method)
    response = None

    try:
        response = _validated_url_response(url, get_method)
        status_code = response.status_code

        if status_code == 200:
            return

        _raise_url_status_error(status_code, url, code, params)
    except ValidationError:
        raise
    except URL_VALIDATION_ERRORS:
        # Not just requests.exceptions.RequestException: malformed-but-
        # valid-looking URLs can raise UnicodeError / LocationParseError,
        # which would otherwise escape as an uncaught 500.
        raise ValidationError(
            URL_REACHABILITY_ERROR,
            code=code,
            params=params,
        )
    finally:
        close_response = getattr(response, "close", None)
        if close_response:
            close_response()


class Status200UrlValidator(URLValidator):
    def __call__(self, value):
        super().__call__(value)
        validate_url_200(value, code=self.code, params={"value": value})
