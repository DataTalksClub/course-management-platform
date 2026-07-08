import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from course_management.observability.events import AppEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentryConfig:
    dsn: str
    environment: str
    release: str
    traces_sample_rate: float
    profiles_sample_rate: float
    send_default_pii: bool


class SentryEventBackend:
    def record(self, event: AppEvent) -> None:
        if not sentry_enabled():
            return

        import sentry_sdk

        sentry_sdk.add_breadcrumb(
            category="app.event",
            message=event.name,
            level="info",
            data=event.normalized_properties(),
        )


def configure_sentry() -> None:
    config = sentry_config()
    if config is None:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=config.dsn,
        environment=config.environment,
        release=config.release,
        traces_sample_rate=config.traces_sample_rate,
        profiles_sample_rate=config.profiles_sample_rate,
        send_default_pii=config.send_default_pii,
    )


def capture_exception(
    exc: BaseException,
    *,
    properties: dict[str, Any] | None = None,
) -> None:
    if not sentry_enabled():
        return

    import sentry_sdk

    with sentry_sdk.push_scope() as scope:
        for key, value in (properties or {}).items():
            scope.set_extra(key, value)
        sentry_sdk.capture_exception(exc)


def sentry_enabled() -> bool:
    return bool(getattr(settings, "SENTRY_DSN", ""))


def sentry_config() -> SentryConfig | None:
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        return None

    return SentryConfig(
        dsn=dsn,
        environment=getattr(settings, "OBSERVABILITY_ENVIRONMENT", "local"),
        release=getattr(settings, "VERSION", ""),
        traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0),
        profiles_sample_rate=getattr(
            settings,
            "SENTRY_PROFILES_SAMPLE_RATE",
            0.0,
        ),
        send_default_pii=getattr(settings, "SENTRY_SEND_DEFAULT_PII", False),
    )
