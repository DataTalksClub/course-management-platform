# Application notifications through Relay

New pending registrations for a course requiring approval create one durable
`ApplicationNotification` per operator. `APPLICATION_NOTIFICATION_OPERATORS`
is a comma-separated deployment setting; `alexey@datatalks.club` is always
included, including when the setting is empty. Addresses are normalized and
deduplicated. Open-course registrations do not notify operators.

Changing an existing registration to approved or rejected creates an applicant
notification in the same database transaction. Cadmin review, the approval
helper, model saves and Django admin bulk approve/reject use this boundary.
Repeating a decision or saving unrelated fields does not enqueue again. A later
changed decision has a new sequence and a new stable Relay idempotency key.
Direct SQL/QuerySet.update bypasses model lifecycle and must not be used for
review decisions. Existing registration and wall rules remain unchanged.

Relay client: `dtc-courses`. Templates use HTML and text bodies in CMP's existing
per-site style, with no new client branding configuration:

- `application-pending-operator`: applicant identity and pending review link.
- `application-approved`: acceptance, course workspace link and instruction to
  sign in using the application email address.
- `application-rejected`: polite cohort rejection, without review internals.

Publish to each environment with its own Relay configuration:

```
uv run python manage.py publish_application_templates
```

The existing scheduled outbox command also processes these notifications, so no
additional scheduler is required. To process just the application queue:

```
uv run python manage.py process_application_notifications --limit 100
```

The queue saves the recipient and context at creation time. Dispatch uses Relay's
transactional endpoint and category, honors `RELAY_TRANSACTIONAL_DRY_RUN`, and
retains its idempotency key across retries/restarts. A process lease and database
advisory lock fence concurrent workers. A network failure, rejected/suppressed
message, malformed acknowledgement or missing Relay configuration sets `failed`,
logs a sanitized error, and emits the existing `datamailer.health_warning` event.
`check_cmp_workers` detects failed notifications and a backlog older than ten
minutes, feeding the existing host operator alert transport. Failed sends retry
after five minutes with the same key. No historical applications are backfilled.
