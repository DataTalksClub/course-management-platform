import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest

logger = logging.getLogger(__name__)


def absolute_url_with_fallback(
    request: HttpRequest, path: str, *, label: str
) -> str:
    """Resolve a path to an absolute URL.

    Prefers settings.PUBLIC_BASE_URL, then the request host, falling back to
    the first concrete ALLOWED_HOSTS entry when the request host is disallowed.
    ``label`` identifies the caller in the fallback warning log.
    """
    if public_base_url := absolute_public_base_url(path):
        return public_base_url

    try:
        return request.build_absolute_uri(path)
    except DisallowedHost:
        return fallback_absolute_url(request, path, label=label)


def absolute_public_base_url(path):
    if not settings.PUBLIC_BASE_URL:
        return ""
    return urljoin(f"{settings.PUBLIC_BASE_URL}/", path.lstrip("/"))


def concrete_allowed_host():
    allowed_hosts = settings.ALLOWED_HOSTS
    for host in allowed_hosts:
        if host and host != "*":
            return host
    return "localhost"


def fallback_absolute_url(request, path, *, label):
    fallback_host = concrete_allowed_host()
    logger.warning(
        "Falling back to ALLOWED_HOSTS for %s update URL "
        "because request host is not allowed: %s",
        label,
        fallback_host,
    )
    return urljoin(f"{request.scheme}://{fallback_host}", path)
