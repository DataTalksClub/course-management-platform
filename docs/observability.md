# Observability

CMP emits structured application events through a small project-owned
observability interface. Product code does not depend directly on a vendor
SDK.

## Current Coolify deployment

The Coolify production and dev compose templates set
`OBSERVABILITY_EVENT_BACKENDS=log`. Events are written to the application
logger and stdout. On Contabo, the Docker log collector forwards container
logs to VictoriaLogs; see the [CMP proxy and log notes](../deploy/coolify/traefik/README.md).
Host log access, proxy access logs, metrics, and alert rules are managed by
the infrastructure operators. For a production incident, follow the
read-only access path in the relevant Hub infrastructure intake and the
[`cmp-incident-response` skill](../.agents/skills/cmp-incident-response/SKILL.md).

The Coolify release target and public hostname determine whether a deployment
is production or dev. The historical `OBSERVABILITY_ENVIRONMENT` label should
not be used to infer the deployment target by itself.

## Event schema

Every event carries these common fields:

- `event`
- `schema_version`
- `environment`
- `release`
- `distinct_id`

Keep event properties small, structured, and portable. Do not include
homework answers, peer-review notes, comments, OAuth provider payloads,
tokens, or other free-form user content.

Application code can record an event with:

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

## Backends

Configure event backends with `OBSERVABILITY_EVENT_BACKENDS`:

- `noop` drops events and is useful in tests.
- `log` writes structured events to the Django logger. This is the backend in
  the current Coolify templates.
- `cloudwatch` emits CloudWatch Embedded Metric Format records. The code and
  `/cadmin/cloudwatch/` dashboard remain available for environments that are
  explicitly configured with CloudWatch access; they are not the current
  Contabo logging or deployment path.

Local development should use:

```bash
OBSERVABILITY_EVENT_BACKENDS=log
OBSERVABILITY_ENVIRONMENT=local
```

## Optional CloudWatch backend

When an environment explicitly uses the `cloudwatch` backend, it emits one
low-cardinality metric:

- Namespace: `CourseManagement/App` by default.
- Metric: `AppEventCount`.
- Dimensions: `environment`, `event`.
- Unit: `Count`.

The `/cadmin/cloudwatch/` page reads those `AppEventCount` metrics with
`GetMetricData`; it does not create metrics or a CloudWatch dashboard resource.
The CloudWatch region comes from `CLOUDWATCH_APP_METRIC_REGION`, falling back
to `AWS_REGION` or `AWS_DEFAULT_REGION`.

The backend can emit events such as `datamailer.health_warning`,
`homework.scoring_failed`, `project.scoring_failed`, `api.auth_failed`, and
`exception`. Detailed event fields remain in the configured log destination;
they are intentionally not metric dimensions to avoid high-cardinality
metrics.

## Datamailer health

Run the health check directly with:

```bash
uv run python manage.py monitoring_datamailer_health --json
```

The command emits a `datamailer.health_checked` event with compact status
fields, including outbox due, pending, retrying, and failed counts. A warning
also emits `datamailer.health_warning`.

In production, the Coolify `health` scheduled job invokes this command through
`python manage.py run_cmp_job health` every five minutes. The job and its
owner are listed in [CMP-WORKERS.md](../deploy/coolify/CMP-WORKERS.md).

## Local checks

Run the focused observability tests with:

```bash
IS_LOCAL=1 uv run pytest data/tests/test_observability.py
```

With the `log` backend, events stay in local application logs and no network
event is sent.

## Adding another backend

The provider boundary is the `EventBackend` protocol in
`course_management/observability/events.py`. To add another provider:

1. Add a backend implementing `record(event: AppEvent)`.
2. Configure dual-write and compare counts and payloads.
3. Switch configuration after the replacement is verified.

The product code that emits events does not need to change.
