import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

FAIL_SUFFIX = "/fail"
START_SUFFIX = "/start"


@dataclass(frozen=True)
class HealthcheckPing:
    url: str
    status: str = "success"
    message: str = ""

    @property
    def ping_url(self) -> str:
        if self.status == "start":
            return f"{self.url.rstrip('/')}{START_SUFFIX}"
        if self.status == "fail":
            return f"{self.url.rstrip('/')}{FAIL_SUFFIX}"
        return self.url


def ping_check(
    url: str,
    *,
    status: str = "success",
    message: str = "",
) -> None:
    if not url:
        return

    ping = HealthcheckPing(url=url, status=status, message=message)
    timeout = getattr(settings, "HEALTHCHECKS_TIMEOUT_SECONDS", 2.0)
    try:
        requests.post(
            ping.ping_url,
            data=ping.message.encode("utf-8"),
            timeout=timeout,
        )
    except requests.RequestException:
        logger.exception("Healthcheck ping failed for status=%s", status)
