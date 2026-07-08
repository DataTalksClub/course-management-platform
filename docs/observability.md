# Observability

The app uses a small project-owned observability abstraction so product code is
not tied directly to any vendor SDK.

Application code should call:

```python
from course_management.observability import record_event

record_event(
    "homework.submitted",
    request=request,
    properties={
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "submission_id": submission.id,
    },
)
```

Provider-specific code lives under `course_management/observability/`.

## Event Schema

Every event carries these common fields:

- `event`
- `schema_version`
- `environment`
- `release`
- `distinct_id`

Keep event properties small, structured, and portable. Do not include homework
answers, peer-review notes, comments, OAuth provider payloads, tokens, or other
free-form user content.

## Backends

Configure event backends with `OBSERVABILITY_EVENT_BACKENDS`.

Supported values:

- `noop`: drops events, useful in tests.
- `log`: writes structured events to the Django logger.
- `posthog`: sends product/audit events to PostHog.
- `sentry`: adds events as Sentry breadcrumbs.

Examples:

```bash
export OBSERVABILITY_EVENT_BACKENDS=log
export OBSERVABILITY_EVENT_BACKENDS=log,posthog
export OBSERVABILITY_EVENT_BACKENDS=log,posthog,sentry
```

Local development should use `log`, which needs no external account.

## Accounts And Keys Needed

Sentry:

- `SENTRY_DSN`
- optional `SENTRY_TRACES_SAMPLE_RATE`
- optional `SENTRY_PROFILES_SAMPLE_RATE`
- optional `SENTRY_SEND_DEFAULT_PII`, default `0`

PostHog:

- `POSTHOG_API_KEY`, project API key
- optional `POSTHOG_HOST`, default `https://us.i.posthog.com`
- optional `POSTHOG_STRICT`, default `0`

Healthchecks.io:

- `HEALTHCHECKS_DATAMAILER_HEALTH_URL`, the ping URL for the Datamailer health
  check.

External uptime:

- No app secret is needed. Configure the monitor in UptimeRobot, StatusCake, or
  Sentry Uptime to check `/api/health/`.

AWS/CloudWatch:

- No app secret is needed beyond the existing ECS logging setup. Configure log
  retention and alarms in AWS.

## Local Testing

Run the focused tests:

```bash
uv run python manage.py test data.tests.test_observability
```

Run the Datamailer health event locally:

```bash
uv run python manage.py monitoring_datamailer_health --json
```

With no PostHog key or Healthchecks URL, these commands do not send network
events.

## Migration Strategy

The provider boundary is the `EventBackend` protocol in
`course_management/observability/events.py`. To move from PostHog to another
system later:

1. Add a new backend implementing `record(event: AppEvent)`.
2. Configure `OBSERVABILITY_EVENT_BACKENDS=log,posthog,new_backend` to dual-write.
3. Compare counts and payloads in both systems.
4. Switch to `OBSERVABILITY_EVENT_BACKENDS=log,new_backend`.

This also supports a later Grafana/Loki/OpenTelemetry/S3 backend without
changing the views or domain logic that emit events.
