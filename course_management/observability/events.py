import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

RESERVED_PROPERTY_KEYS = {
    "event",
    "environment",
    "release",
    "schema_version",
    "distinct_id",
}


@dataclass(frozen=True)
class AppEvent:
    name: str
    distinct_id: str
    properties: dict[str, Any] = field(default_factory=dict)

    def normalized_properties(self) -> dict[str, Any]:
        normalized = {
            "event": self.name,
            "schema_version": event_schema_version(),
            "environment": observability_environment(),
            "release": observability_release(),
        }
        for key, value in self.properties.items():
            if key in RESERVED_PROPERTY_KEYS:
                normalized[f"app_{key}"] = value
                continue
            normalized[key] = value
        return normalized


class EventBackend(Protocol):
    def record(self, event: AppEvent) -> None:
        pass


def observability_environment() -> str:
    return getattr(settings, "OBSERVABILITY_ENVIRONMENT", "local")


def observability_release() -> str:
    return getattr(settings, "VERSION", "")


def event_schema_version() -> str:
    return getattr(settings, "OBSERVABILITY_EVENT_SCHEMA_VERSION", "1")


def record_event(
    name: str,
    *,
    request=None,
    user=None,
    distinct_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    event = AppEvent(
        name=name,
        distinct_id=resolved_distinct_id(
            request=request,
            user=user,
            distinct_id=distinct_id,
        ),
        properties=event_properties(request=request, properties=properties),
    )
    for backend in configured_event_backends():
        try:
            backend.record(event)
        except Exception:
            logger.exception(
                "observability backend failed for event=%s",
                event.name,
            )


def report_exception(
    exc: BaseException,
    *,
    name: str = "exception",
    request=None,
    user=None,
    properties: dict[str, Any] | None = None,
) -> None:
    record_event(
        name,
        request=request,
        user=user,
        properties=properties,
    )
    capture_exception_with_error_tracker(exc, properties or {})


def resolved_distinct_id(
    *,
    request=None,
    user=None,
    distinct_id: str | None = None,
) -> str:
    if distinct_id:
        return distinct_id

    resolved_user = user
    if resolved_user is None and request is not None:
        resolved_user = getattr(request, "user", None)

    if getattr(resolved_user, "is_authenticated", False):
        return f"user:{resolved_user.pk}"

    return "anonymous"


def event_properties(
    *,
    request=None,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(properties or {})
    if request is None:
        return result

    path = getattr(request, "path", "")
    method = getattr(request, "method", "")
    if path:
        result.setdefault("path", path)
    if method:
        result.setdefault("method", method)
    return result


def configured_event_backends() -> list[EventBackend]:
    backends = []
    backend_names = getattr(settings, "OBSERVABILITY_EVENT_BACKENDS", ["log"])
    for backend_name in backend_names:
        backend = event_backend(backend_name)
        if backend is not None:
            backends.append(backend)
    return backends


def event_backend(name: str) -> EventBackend | None:
    normalized_name = name.strip().lower()
    if normalized_name == "noop":
        return NoopEventBackend()
    if normalized_name == "log":
        return LogEventBackend()
    if normalized_name == "posthog":
        from course_management.observability.posthog import PostHogEventBackend

        return PostHogEventBackend()
    if normalized_name == "sentry":
        from course_management.observability.sentry import SentryEventBackend

        return SentryEventBackend()

    logger.warning("Unknown observability event backend: %s", name)
    return None


class LogEventBackend:
    def record(self, event: AppEvent) -> None:
        extra = event.normalized_properties()
        extra["distinct_id"] = event.distinct_id
        logger.info("app_event", extra=extra)


class NoopEventBackend:
    def record(self, event: AppEvent) -> None:
        return


def capture_exception_with_error_tracker(
    exc: BaseException,
    properties: dict[str, Any],
) -> None:
    from course_management.observability.sentry import capture_exception

    capture_exception(exc, properties=properties)
