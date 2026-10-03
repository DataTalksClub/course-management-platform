# CMP → Relay migration (October 2026)

CMP's email backend moved from the old Datamailer sandbox
(`datamailer.dtcdev.click`) to Relay production
(`https://relay.datatalks.club`). Relay exposes the same client API
surface (`/api/contacts`, `/api/recipient-lists/*`,
`/api/transactional/*`, `/api/campaigns/*`), so CMP's client code is
unchanged apart from configuration naming. Datamailer's API docs live on
in `docs/datamailer-integration.md` as the conceptual reference.

## Configuration

CMP reads `RELAY_*` environment variables (see `course_management/settings.py`):

```bash
RELAY_URL=https://relay.datatalks.club
RELAY_API_KEY=<client key for the dtc-courses client>
RELAY_CLIENT=dtc-courses
RELAY_AUDIENCE=dtc-courses
RELAY_FROM_EMAIL=courses
RELAY_WEBHOOK_TOKEN=<token Relay sends on contact-event callbacks>
```

`courses` resolves against the Relay client's sender list:
`courses=DataTalks.Club Courses <courses@datatalks.club>` (alias routes to
alexey@datatalks.club). `no-reply@datatalks.club` is configured as well.

On AWS, the ECS task definitions (repo `aws-infra`, `main/cmp/`) set
`RELAY_URL`/`RELAY_CLIENT`/`RELAY_AUDIENCE`/`RELAY_FROM_EMAIL` and pull
`RELAY_API_KEY` and `RELAY_WEBHOOK_TOKEN` from Secrets Manager:

- `course-management/relay-api-key`
- `course-management/relay-webhook-token`

## What was migrated

| Data | How |
| --- | --- |
| 33,839 contacts (subscriptions, tags, verification, validation, suppression incl. 125 hard bounces) | `GET /api/contacts` export from Datamailer → `POST /api/contacts/imports` into Relay (idempotent upserts) |
| Category preferences (submission-results, deadline-reminders, course-updates) | Per-contact `GET /api/contacts/preferences` from Datamailer; non-default sets re-`PUT` on Relay |
| Transactional templates (8 CMP-owned keys) | `uv run python manage.py upsert_datamailer_templates` against Relay |
| Recipient lists | Not copied. CMP rebuilds them from its own database (`sync_datamailer_recipient_lists`, `audit_datamailer_recipient_lists --repair`), and every send-time flow bulk-syncs its members immediately before sending |

Historical email events and campaigns were not migrated; Relay starts
with a fresh history for the `dtc-courses` client.

## Edge limits (relay.datatalks.club)

Relay's CloudFront terminates AWS WAF:

- Request bodies over 8 KiB are rejected (managed common rule set).
- A per-IP rate limit applies (300 requests / 5 minutes in the reference
  config).
- The common rule set's `CrossSiteScripting_BODY` rule false-positives on
  inline CSS: any request body containing `style="..."` (every CMP email
  template's `html_body`, and campaign bodies with styled HTML) is
  rejected with 403. aws-infra `main/relay/edge.tf` counts this rule
  instead of blocking it; **until that change is applied** (needs AWS),
  template publishing through the WAF is blocked, so
  `upsert_datamailer_templates` fails on styled templates.

CMP's client chunks member-array payloads (transient reminder lists,
bulk member syncs) under the body limit — see
`course_management/datamailer/client_chunking.py`. Bulk scripts against
the Relay API must pace themselves (~1 request/second).

## Webhook (Relay → CMP)

Relay posts contact events (unsubscribe, bounce, complaint, delivery
lifecycle) to `https://courses.datatalks.club/api/datamailer/events`
with `Authorization: Bearer <cmp_webhook_token>`; CMP validates the
token against `RELAY_WEBHOOK_TOKEN`. The endpoint path keeps its
historical name.

## Remaining steps (need AWS access)

The AWS Gate was closed during the migration, so these apply-time steps
are pending:

1. Create the Secrets Manager secrets:
   ```bash
   aws secretsmanager create-secret --name course-management/relay-api-key \
     --secret-string '<the cmp-production client key>'
   aws secretsmanager create-secret --name course-management/relay-webhook-token \
     --secret-string '<token from the migration record>'
   ```
2. Apply terraform in `aws-infra` (`main/relay` for the WAF rule change,
   `main/cmp` for the task-definition env), then redeploy CMP dev/prod.
3. After the WAF change is live, republish the three templates whose
   inline CSS the WAF was blocking (`peer-review-assignment`,
   `registration-confirmation`, and refresh
   `certificate-availability-notification`):
   `uv run python manage.py upsert_datamailer_templates`
4. Recipient lists rebuild from CMP data on first use; to pre-populate,
   run `sync_datamailer_recipient_lists` against the deployed
   environment (large lists via `--import-by-reference`).
