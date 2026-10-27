# Application notifications through Relay

New registrations no longer notify operators individually. Operators receive
one daily registration digest instead (see below). `APPLICATION_NOTIFICATION_OPERATORS`
is a comma-separated deployment setting; `alexey@datatalks.club` is always
included, including when the setting is empty. Addresses are normalized and
deduplicated. The digest covers every new registration regardless of the
course wall setting.

Changing an existing registration to approved or rejected creates an applicant
notification in the same database transaction. Cadmin review, the approval
helper, model saves and Django admin bulk approve/reject use this boundary.
Repeating a decision or saving unrelated fields does not enqueue again. A later
changed decision has a new sequence and a new stable Relay idempotency key.
Direct SQL/QuerySet.update bypasses model lifecycle and must not be used for
review decisions. Existing registration and wall rules remain unchanged.

Relay client: `dtc-courses`. Templates use HTML and text bodies in CMP's existing
per-site style, with no new client branding configuration:

- `application-pending-operator`: retained for already-queued rows only; new
  registrations no longer create it.
- `registration-digest-operator`: daily digest, grouped by course with count,
  name, email and confirmed/unconfirmed state per registrant, plus totals.
- `application-approved`: acceptance, course workspace link and instruction to
  sign in using the application email address.
- `application-rejected`: polite cohort rejection, without review internals.
- `registration-confirmation-reminder-1`: first reminder 24h after an
  unconfirmed registration (confirmation link + course title).
- `registration-confirmation-reminder-2`: final reminder 72h after an
  unconfirmed registration (confirmation link + 7-day deletion deadline).

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
minutes, feeding the existing host operator alert transport. Transient failures
retry after five minutes with the same key; permanent Relay 4xx (for example an
unknown `template_key`) backs off 24h to avoid hot retry loops. Confirmation
reminders use the same policy via `confirmation_reminder_next_attempt_at`:
transient 5min, permanent 4xx 24h. No historical applications are backfilled.
Provision new template keys in each environment before they send:

## Daily registration digest

The minutely `process_datamailer_outbox` schedule calls
`maybe_send_scheduled_digest()`: once per Europe/Berlin day after 09:00 it
sends one digest covering the previous 24h of registrations (`created_at` in
`[now - 24h, now)`), grouped by course with per-course pending-review links.
One `RegistrationDigestSend` row per Berlin date makes the send idempotent:
restarts and rolling overlap reuse the same Relay idempotency keys
(`cmp-registration-digest:<date>:<recipient slot>`) and never record or send
the same day twice. A `--force` resend reuses the same keys.

When the window holds zero registrations no email is sent; a `skipped_empty`
row records the decision (this is the chosen zero-case behavior). The window
is always the literal previous 24h, so on the Europe/Berlin DST switch days
it shifts by one hour against local midnight; the Berlin date still changes
exactly once per day. Digest trouble never blocks the outbox: failures are logged with a sanitized error,
emit `datamailer.health_warning`, mark the `digest` job failed for the
`check_cmp_workers` 26h alarm, and retry on the next minute tick. Manual use:

```
uv run python manage.py send_registration_digest --dry-run
uv run python manage.py send_registration_digest --force
```
