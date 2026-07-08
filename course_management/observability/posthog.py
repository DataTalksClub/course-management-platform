import logging
from dataclasses import dataclass

import requests
from django.conf import settings

from course_management.observability.events import AppEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostHogConfig:
    api_key: str
    host: str
    timeout_seconds: float
    strict: bool = False

    @property
    def capture_url(self) -> str:
        return f"{self.host.rstrip('/')}/capture/"


class PostHogEventBackend:
    def record(self, event: AppEvent) -> None:
        config = posthog_config()
        if config is None:
            return

        payload = {
            "api_key": config.api_key,
            "event": event.name,
            "distinct_id": event.distinct_id,
            "properties": event.normalized_properties(),
        }
        try:
            response = requests.post(
                config.capture_url,
                json=payload,
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("PostHog event delivery failed")
            if config.strict:
                raise


def posthog_config() -> PostHogConfig | None:
    api_key = getattr(settings, "POSTHOG_API_KEY", "")
    if not api_key:
        return None

    host = getattr(settings, "POSTHOG_HOST", "https://us.i.posthog.com")
    timeout_seconds = getattr(settings, "POSTHOG_TIMEOUT_SECONDS", 2.0)
    strict = getattr(settings, "POSTHOG_STRICT", False)
    return PostHogConfig(
        api_key=api_key,
        host=host,
        timeout_seconds=timeout_seconds,
        strict=strict,
    )
