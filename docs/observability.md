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

### Sentry

Use Sentry for Django exceptions, release visibility, and error breadcrumbs.

Register:

- https://sentry.io/signup/

Create:

- Organization: `DataTalksClub`, or the closest existing org name.
- Project platform: Django or Python.
- Project name suggestion: `course-management-platform`.

Find the key:

- Open the project in Sentry.
- Go to project settings.
- Open **Client Keys (DSN)**.
- Copy the DSN.

Set:

- `SENTRY_DSN`
- optional `SENTRY_TRACES_SAMPLE_RATE`
- optional `SENTRY_PROFILES_SAMPLE_RATE`
- optional `SENTRY_SEND_DEFAULT_PII`, default `0`

Recommended initial values:

```bash
SENTRY_DSN="<copy from Sentry Client Keys (DSN)>"
SENTRY_TRACES_SAMPLE_RATE=0
SENTRY_PROFILES_SAMPLE_RATE=0
SENTRY_SEND_DEFAULT_PII=0
```

Keep PII disabled until we explicitly review what should be attached to error
reports.

Docs:

- https://docs.sentry.io/concepts/key-terms/dsn-explainer/
- https://docs.sentry.io/platforms/python/integrations/django/

### PostHog

Use PostHog for product/audit events: logins, registrations, homework/project
submissions, peer reviews, scoring events, and Datamailer health events.

Register:

- https://app.posthog.com/signup

Create:

- Organization: `DataTalksClub`, or the closest existing org name.
- Project name suggestion: `course-management-platform`.
- Region/host: use the same region you choose in PostHog. The default in this
  app is US: `https://us.i.posthog.com`.

Find the key:

- Open the PostHog project.
- Go to project settings.
- Copy the **Project API key** / project token. It usually starts with `phc_`.
- Copy the instance host if it is not `https://us.i.posthog.com`.

Do not use a PostHog personal API key for `POSTHOG_API_KEY`. Personal keys can
grant account-level API access; this integration only needs the project API key
used for event capture.

Set:

- `POSTHOG_API_KEY`, project API key
- optional `POSTHOG_HOST`, default `https://us.i.posthog.com`
- optional `POSTHOG_STRICT`, default `0`

Recommended initial values:

```bash
POSTHOG_API_KEY="<project API key, usually phc_...>"
POSTHOG_HOST="https://us.i.posthog.com"
POSTHOG_STRICT=0
```

Docs:

- https://posthog.com/docs/libraries/python
- https://posthog.com/docs/api/personal-api-keys

### Healthchecks.io

Use Healthchecks.io for scheduled/background heartbeat monitoring. The first
check is for Datamailer health.

Register:

- https://healthchecks.io/

Create:

- Project name suggestion: `course-management-platform`.
- Check name suggestion: `cmp-datamailer-health-dev` for dev.
- Add another later for prod: `cmp-datamailer-health-prod`.
- Schedule period: match the schedule used to run
  `monitoring_datamailer_health`. A 15- or 30-minute period is a reasonable
  starting point.

Find the key:

- Open the check.
- Copy the ping URL, usually `https://hc-ping.com/<uuid>`.

Set:

- `HEALTHCHECKS_DATAMAILER_HEALTH_URL`, the ping URL for the Datamailer health
  check.

Recommended initial value:

```bash
HEALTHCHECKS_DATAMAILER_HEALTH_URL="https://hc-ping.com/<uuid>"
```

Docs:

- https://healthchecks.io/docs/
- https://healthchecks.io/docs/http_api/
- https://healthchecks.io/docs/configuring_checks/

### External Uptime

Use UptimeRobot, StatusCake, or Sentry Uptime for public HTTP checks. This does
not require an app key.

Register one provider:

- UptimeRobot: https://uptimerobot.com/
- StatusCake: https://www.statuscake.com/
- Or use Sentry Uptime inside the same Sentry project.

Create HTTP checks:

- Dev health: `https://dev.courses.datatalks.club/api/health/`
- Production health, when ready: `https://courses.datatalks.club/api/health/`
- Optional public page checks for one or two active course pages.

Expected health response:

```json
{
  "status": "ok",
  "version": "<deployed version>"
}
```

- No app secret is needed. Configure the monitor in UptimeRobot, StatusCake, or
  Sentry Uptime to check `/api/health/`.

### AWS/CloudWatch

- No app secret is needed beyond the existing ECS logging setup. Configure log
  retention and alarms in AWS.

## Key Request Template

Send these values for dev first:

```bash
OBSERVABILITY_ENVIRONMENT=dev
SENTRY_DSN=
POSTHOG_API_KEY=
POSTHOG_HOST=https://us.i.posthog.com
HEALTHCHECKS_DATAMAILER_HEALTH_URL=
```

Optional, keep these defaults unless we decide otherwise:

```bash
OBSERVABILITY_EVENT_BACKENDS=log,posthog,sentry
SENTRY_TRACES_SAMPLE_RATE=0
SENTRY_PROFILES_SAMPLE_RATE=0
SENTRY_SEND_DEFAULT_PII=0
POSTHOG_STRICT=0
```

After dev is verified, provide the same set for production with:

```bash
OBSERVABILITY_ENVIRONMENT=production
```

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
