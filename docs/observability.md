# Observability

The app uses a small project-owned observability abstraction so product code is
not tied directly to any vendor or AWS SDK.

For now, CloudWatch is the only deployed observability provider. The app emits
structured events to stdout, ECS sends those logs to CloudWatch Logs, and the
CloudWatch backend emits Embedded Metric Format records so CloudWatch can create
metrics and alarms from the same event stream.

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
- `cloudwatch`: writes CloudWatch Embedded Metric Format event counters.

Local development should use:

```bash
OBSERVABILITY_EVENT_BACKENDS=log
OBSERVABILITY_ENVIRONMENT=local
```

Deployed AWS environments should use:

```bash
OBSERVABILITY_EVENT_BACKENDS=cloudwatch
OBSERVABILITY_ENVIRONMENT=dev
CLOUDWATCH_APP_METRIC_NAMESPACE=CourseManagement/App
```

Use `OBSERVABILITY_ENVIRONMENT=production` in production.

## CloudWatch Metrics

The `cloudwatch` backend emits one low-cardinality metric:

- Namespace: `CourseManagement/App` by default.
- Metric: `AppEventCount`.
- Dimensions: `environment`, `event`.
- Unit: `Count`.

This lets CloudWatch alert on events such as:

- `datamailer.health_warning`
- `homework.scoring_failed`
- `project.scoring_failed`
- `project.peer_reviews_assignment_failed`
- `datamailer.outbox_failed`
- `datamailer.outbox_dispatch_failed`
- `api.auth_failed`
- `exception`

Detailed fields such as `course_slug`, `homework_slug`, `project_slug`,
`submission_id`, `release`, and `distinct_id` remain in CloudWatch Logs for
Logs Insights queries. They are intentionally not metric dimensions to avoid
high-cardinality custom metric cost.

## Datamailer Health

Run this command on a schedule:

```bash
uv run python manage.py monitoring_datamailer_health --json
```

The command emits a `datamailer.health_checked` event with compact status
fields:

- `outbox_due_count`
- `outbox_pending_count`
- `outbox_retrying_count`
- `outbox_failed_count`
- `send_failed_count`
- `callback_duplicate_count`

If the status is not `ok`, the command also emits
`datamailer.health_warning`. Use that event for direct CloudWatch alarms.

In AWS, schedule this with EventBridge Scheduler or an EventBridge rule that
runs the CMP ECS task with a command override.

## Accounts And Keys

No Sentry, PostHog, Healthchecks.io, Grafana, or third-party observability
account is required.

CloudWatch uses the existing AWS account and ECS log shipping. For deployment,
we need:

- AWS account access for Terraform in `aws-infra/main/cmp`.
- Existing GitHub Actions AWS credentials for CMP releases.
- An alert email in Terraform variable `alert_email`. AWS sends a confirmation
  email for the SNS subscription; alerts are not delivered until it is
  confirmed.

## ECS Environment

Set these variables on both live CMP ECS task definitions with the existing ECS
environment-variable update script:

Dev:

```bash
OBSERVABILITY_EVENT_BACKENDS=cloudwatch
OBSERVABILITY_ENVIRONMENT=dev
CLOUDWATCH_APP_METRIC_NAMESPACE=CourseManagement/App
```

Production:

```bash
OBSERVABILITY_EVENT_BACKENDS=cloudwatch
OBSERVABILITY_ENVIRONMENT=production
CLOUDWATCH_APP_METRIC_NAMESPACE=CourseManagement/App
```

The Terraform task definition files include these values, but the ECS task
definitions currently use `ignore_changes = [container_definitions]`, because
CI/CD owns image and env updates at release time. That means Terraform will not
overwrite the live task definition env vars by itself.

## Logs Insights

Useful starter queries:

```sql
fields @timestamp, event, environment, release, course_slug, homework_slug, project_slug
| filter message = "app_event" or message = "cloudwatch_app_event"
| sort @timestamp desc
| limit 100
```

Registrations by course:

```sql
filter event = "registration.submitted"
| stats count(*) as registrations by bin(1h), course_slug
| sort bin(1h) desc
```

Homework submissions by course/homework:

```sql
filter event = "homework.submitted"
| stats count(*) as submissions by bin(1h), course_slug, homework_slug
| sort bin(1h) desc
```

Project submissions by course/project:

```sql
filter event = "project.submitted"
| stats count(*) as submissions by bin(1h), course_slug, project_slug
| sort bin(1h) desc
```

Failures by release:

```sql
filter event like /failed|rejected|unauthorized/
| stats count(*) as failures by release, event
| sort failures desc
```

Datamailer status:

```sql
filter event = "datamailer.health_checked"
| fields @timestamp, status, outbox_due_count, outbox_retrying_count,
    outbox_failed_count, send_failed_count, callback_duplicate_count
| sort @timestamp desc
| limit 50
```

## Alerts

Create CloudWatch alarms on the `AppEventCount` metric with dimensions
`environment` and `event`.

Recommended first alarms for dev:

- `datamailer.health_warning > 0` in 5 minutes.
- `exception > 0` in 5 minutes.
- `datamailer.outbox_failed > 0` in 5 minutes.
- `datamailer.outbox_dispatch_failed > 0` in 5 minutes.
- `homework.scoring_failed > 0` in 5 minutes.
- `project.scoring_failed > 0` in 5 minutes.
- `project.peer_reviews_assignment_failed > 0` in 5 minutes.
- `api.auth_failed` above a small threshold, for example `>= 10` in 5 minutes.

Configured AWS/service alarms in `aws-infra`:

- ALB 5xx count.
- ALB target response time.
- ALB unhealthy targets.

Useful next AWS/service alarms:

- ECS desired task count not met.
- ECS task restarts/deploy failures.
- RDS CPU/storage/connections.
- CloudWatch Synthetics or another public check for `/api/health/` if we want
  release/version monitoring inside CloudWatch instead of only GitHub e2e smoke.

## Local Testing

Run the focused tests:

```bash
uv run python manage.py test data.tests.test_observability
```

Run the Datamailer health event locally:

```bash
uv run python manage.py monitoring_datamailer_health --json
```

With no AWS log shipping locally, the command only prints/logs locally and does
not send network events.

## Migration Strategy

The provider boundary is the `EventBackend` protocol in
`course_management/observability/events.py`. To move from CloudWatch to another
system later:

1. Add a new backend implementing `record(event: AppEvent)`.
2. Configure dual-write, for example
   `OBSERVABILITY_EVENT_BACKENDS=cloudwatch,new_backend`.
3. Compare counts and payloads in both systems.
4. Switch backend configuration when the replacement is verified.

The app code that emits events does not need to change.
