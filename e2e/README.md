# E2E smoke tests (Playwright)

End-to-end smoke suite that runs against a **live** CMP deployment (dev by
default) after each deploy. It provisions a full course lifecycle, exercises
the user-facing flows through a real browser, verifies scoring + leaderboard,
and tears the data down again so dev stays clean.

This suite is intentionally **separate from the Django unit tests**
(`courses/tests`, `api/tests`, ...). It has its own `pytest.ini`, never sets
`DJANGO_SETTINGS_MODULE`, and never touches the project database — it only
talks to the remote server over HTTP and a browser.

## Framework

- **Python Playwright + pytest** (`playwright>=1.58.0`, already in the repo's
  dev deps). Chosen over the JS runner so the suite stays in one language /
  one toolchain with the rest of the repo (`uv`, `pytest`), can import nothing
  from Django but reuse the same `.env`, and so CI only needs the existing
  Python environment.
- Provisioning, scoring, assertions and teardown go through the **REST API**
  (fast, token-auth). The genuinely user-facing flows — admin login,
  impersonation, homework/project submission forms, confirmation pages,
  dashboards, leaderboards — go through the **browser**.

## What it covers (issue #194)

| Scenario | File | Driver |
|----------|------|--------|
| 1. Availability & auth (health, admin login, protected redirect) | `tests/test_00_availability.py` | API + browser |
| 2. Course & content provisioning (course, homework w/ FF+CB+MC, project) | `tests/test_01_provisioning.py` | API |
| 3. Enrollment & identity (create/find student, impersonate, profile) | `tests/test_02_enrollment.py` | browser (loginas) |
| 4. Homework flow (submit via UI, confirmation, score, leaderboard) | `tests/test_03_homework.py` | browser + API |
| 5. Project flow (submit via UI, assign reviews, score, stats) | `tests/test_04_project.py` | browser + API |
| 6. Email verification (homework + project confirmation emails) | `tests/test_03/04` (`@pytest.mark.email`) + `tests/test_06` (client unit tests) | real SES round-trip (default) / mock-store (opt-in) |
| 7. Dashboards & stats render | `tests/test_05_dashboards.py` | browser |
| 8. Teardown + pre-run sweep + clean assert | `tests/test_99_teardown.py` | browser + API |

### Email verification: two backends behind one interface

Email checks go through `mock_inbox.py`, which exposes two backends with the
same `wait_for_message(address, template_key=..., subject=...) -> InboxMessage`
interface plus `clear(address)` (teardown):

- **`RealInboxClient` (default).** A real HTTP client for the Datamailer
  **real-inbox** (SES-inbound) API. The student's address is a *real-inbox
  address* (`e2e+<tag>@mailer.dtcdev.click`): Datamailer **really sends via
  SES**, an SES receipt rule writes the raw MIME to S3, and this client reads it
  back — proving the student genuinely received the email. This is the usual
  delivery path, identical in dev and prod (there is a single shared
  Datamailer). Contract (base URL = the Datamailer service root, `Bearer`
  client key):
  - `GET /api/inbox/messages?address=<addr>&limit=25` → newest-first summaries (`s3_key`, `from_email`, `to`, `subject`, `received_at`)
  - `GET /api/inbox/messages/{s3_key}?address=<addr>` → `{message:{…, html_body, text_body, spam_verdict, virus_verdict}}`
  - `DELETE /api/inbox/messages` `{address}` → `{deleted_count}`

  Received MIME has **no `template_key`** (it's not a Datamailer row), so the
  email tests match on `subject` + `body_contains` for this backend.
- **`MockInboxClient` (opt-in).** A real HTTP client for the Datamailer
  **mock-inbox** API. Sends to a *mock address* (`e2e+<tag>@mailbox.test`) are
  captured as `TransactionalMessage` rows **without** real delivery, and this
  client lists / fetches detail / clears them. Use it only via
  `@pytest.mark.mock_inbox` when you want the fast, no-SES path.
  - `GET /api/mock-inbox/messages?address=<addr>&limit=25` → newest-first summaries
  - `GET /api/mock-inbox/messages/{id}` → `{message:{…, html_body, text_body, context, metadata}}`
  - `DELETE /api/mock-inbox/messages` `{address}` → `{deleted_count}`

**Backend selector.** The `email_backend` fixture resolves to `real_inbox` by
default; a test marked `@pytest.mark.mock_inbox` (or parametrized with
`"mock"`) resolves to `mock_inbox`.

**What runs now vs. what's gated.** The client logic is covered by
`tests/test_06_mock_inbox_client.py` (no-network unit tests — paths, auth,
params, response shapes, poll/timeout, retries, disabled-deployment 404,
clear — for **both** backends). The **live** email assertions in `test_03/04`
need the real inbox **enabled on the Datamailer deployment**
(`REAL_INBOX_ENABLED=1` + `REAL_INBOX_S3_BUCKET`; `datamailer-infra` provisions
the SES receipt rule + inbound S3). `E2E_REAL_INBOX_*` falls back to
`DATAMAILER_URL` / `DATAMAILER_API_KEY`. When unset, or when the deployment has
the real inbox off (`404 real_inbox_disabled`), the email tests **xfail** (a
fast pre-check avoids burning the poll timeout) so the suite stays green until
the read API is switched on.

The student email is set to a unique per-run real-inbox address
(`settings.real_address(namespace)` → `e2e+<namespace>@mailer.dtcdev.click`) and
the captured messages are cleared via the `DELETE` endpoint in each email test's
teardown.

### Teardown deletes the course via the Django admin UI

The platform deliberately exposes **no course DELETE API endpoint** — a
standing remote delete capability could let any API client/agent wipe too much
data. Cleanup instead reuses the suite's authenticated admin Playwright session
(the same one used for login + impersonation) and deletes the course through
the **Django admin confirmation screen**
(`/admin/courses/course/<pk>/delete/` → "Yes, I'm sure"). Deleting the `Course`
cascades to **all** of its data (homeworks, questions, projects, submissions,
answers, enrollments, peer reviews are all `on_delete=CASCADE`), so a single
admin delete fully purges a run.

So teardown:

1. removes the student's project submission via the UI (the only remote way
   to delete a submission), then stops impersonating;
2. runs a best-effort API pre-pass on individually-deletable homeworks/projects
   (informative only — the admin delete supersedes it);
3. **deletes the course through the admin UI**, cascading everything away. The
   course pk is resolved from the slug via the admin changelist (the API does
   not return a course id). The next run's **pre-run sweep** admin-deletes any
   stale `e2e-smoke-*` courses the same way.

Teardown stays robust: if the admin delete is unavailable (no admin creds) or
fails, it falls back to **parking** the course (`visible=false`, renamed
`[DELETED] ...`) and reports the residual, so dev still stays clean.

The post-run assertions verify **no _visible_ `e2e-smoke-*` course remains**
and that the course is **fully purged** (no longer retrievable via the API).
The full-purge check requires admin creds; in the API-only subset it is
skipped (the course is parked hidden instead).

> **Teardown now depends on `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD`.** These
> were already required for the browser login/impersonation flows; the admin
> deletion in teardown uses the same session. Without them, teardown degrades
> to the park-hidden fallback.

## Running it

From the **repo root**, using `uv` (repo convention):

```bash
# Everything (needs admin creds + token; see env vars below)
cd e2e && uv run --project .. pytest -c pytest.ini

# Just the no-credential availability checks (health, login page, redirect)
cd e2e && uv run --project .. pytest -c pytest.ini tests/test_00_availability.py
```

Browser-driven tests **skip cleanly** (not error) when admin credentials are
absent, so you can always run the API-only subset.

First-time only, install the browser binary:

```bash
uv run playwright install chromium
```

## Required environment variables / CI secrets

Copy `e2e/.env.example` to `e2e/.env` for local runs, or provide as CI
secrets. The suite also falls back to the **repo-root `.env`** for
`DEV_AUTH_TOKEN` and `PUBLIC_BASE_URL`.

| Var | Required for | Notes |
|-----|--------------|-------|
| `E2E_BASE_URL` | all | Defaults to `https://dev.courses.datatalks.club` (or `PUBLIC_BASE_URL`). |
| `E2E_API_TOKEN` | provisioning/scoring/teardown | Staff token. Falls back to `DEV_AUTH_TOKEN`. |
| `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | browser flows + teardown | Staff account; logs in via the admin form (no OAuth). Teardown deletes the course through the admin UI with this session; without it, teardown only parks the course hidden. |
| `E2E_STUDENT_EMAIL` / `E2E_STUDENT_PASSWORD` | optional | If unset, a per-run `e2e+<namespace>@mailer.dtcdev.click` real-inbox student is created admin-side (really receives the email via SES). |
| `E2E_REAL_INBOX_URL` / `E2E_REAL_INBOX_API_KEY` | email checks (default) | Datamailer service root + client key. Fall back to `DATAMAILER_URL` / `DATAMAILER_API_KEY`. Email tests xfail when the real inbox is unset or disabled on the deployment. |
| `E2E_REAL_INBOX_DOMAIN` / `E2E_REAL_INBOX_TAG` | optional | Real-inbox address shape; default `mailer.dtcdev.click` / `e2e`. Must match the datamailer `REAL_INBOX_*` settings. |
| `E2E_MOCK_INBOX_URL` / `E2E_MOCK_INBOX_API_KEY` | email checks (opt-in `@pytest.mark.mock_inbox`) | Datamailer service root + client key. Fall back to `DATAMAILER_URL` / `DATAMAILER_API_KEY`. |
| `E2E_MOCK_INBOX_DOMAIN` / `E2E_MOCK_INBOX_TAG` | optional | Mock-address shape; default `mailbox.test` / `e2e`. Must match the datamailer `MOCK_INBOX_*` settings. |
| `E2E_EXPECTED_VERSION` | optional | If set, asserts `/api/health/` version matches the just-deployed build. |
| `E2E_HEADLESS` | optional | `0` to watch the browser locally. |

**Never hardcode secrets.** Nothing in this suite contains credentials.

## Scheduling (post dev-deploy)

Run the suite as a **post-deploy job** in the dev deploy workflow (see
`.github/workflows/e2e-smoke-dev.yml`): it triggers on `workflow_run`
completion of the dev deploy, waits for `/api/health/` to report the new
version (`E2E_EXPECTED_VERSION`), runs the suite, and fails (alerting) with
the exact scenario that broke. Alternatively, an EventBridge schedule
(consistent with the deadline-reminder infra) can invoke the same command.
