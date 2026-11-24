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

Approving a referred registration (``referred_by`` set from the invite link
or the "who invited you?" form field) also awards the inviter's enrollment
3 bonus leaderboard points, exactly once per invitee (``ReferralReward``).

Relay client: `dtc-courses`. Templates use HTML and text bodies in CMP's existing
per-site style, with no new client branding configuration:

- `application-pending-operator`: retained for already-queued rows only; new
  registrations no longer create it.
- `registration-digest-operator`: daily digest, grouped by course with count,
  name, email and confirmed/unconfirmed state per registrant, plus totals.
- `application-approved`: acceptance, course workspace link and instruction to
  sign in using the application email address.
- `application-rejected`: polite cohort rejection, without review internals.
- Both decision templates render an optional reviewer `custom_message`
  (e.g. a workshop announcement). It is queued into the notification
  context by cadmin review (single or approve-all-pending) and defaults
  to empty; migration `0063` backfills it on older queued rows.
- `registration-confirmation-reminder-1`: first reminder 24h after an
  unconfirmed registration (confirmation link + course title).
- `registration-confirmation-reminder-2`: final reminder 72h after an
  unconfirmed registration (confirmation link + 7-day deletion deadline).

Validate placeholder values against every registered template
(without sending anything):

```
uv run python manage.py check_transactional_templates
```

Add ``--live`` to also dry-run render each template in Relay (needs Relay
configuration). Template bodies live in Relay and are edited there; this
repo owns only the placeholder values each template receives.

### Reading the live templates

A milestone review starts by reading the bodies back from Relay. The CMP
client key for ``dtc-courses`` (``RELAY_API_KEY``) can read them; no admin key
is needed:

```bash
export DATAMAILER_URL=https://relay.datatalks.club
export DATAMAILER_API_KEY=<dtc-courses client key>   # never commit it

relay api GET /api/transactional/templates                                 # every key and latest_version
relay api GET /api/transactional/templates/application-approved            # current draft
relay api GET /api/transactional/templates/application-approved/versions   # published bodies, newest first
```

Sends render the newest **published** version, so review ``versions[0]`` and
not the draft. With plain curl the header must be
``Authorization: Bearer <key>``. Relay answers ``401`` with a code that names
the mistake: ``missing_authorization`` (no header), ``invalid_api_key``
(wrong key), ``invalid_authorization`` (key sent without ``Bearer``, for
example as ``Token``), ``invalid_admin_api_key`` (client key used on the
admin API that ``relay operator`` calls).

The acceptance email also carries course text that CMP builds when the
notification is queued, from the course record: ``Course starts`` or ``The
course has already started`` (chosen from the start date), the live session
schedule details and URL, the GitHub repository and the help channel. Edit
those on the Course in Django admin; no deploy is needed. Remove a passed
event page there at each milestone, the same as in the Relay bodies.

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
