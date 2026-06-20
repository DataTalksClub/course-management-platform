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
| 6. Email verification (homework + project confirmation emails) | `tests/test_03/04` (`@pytest.mark.email`) + `tests/test_06` (client unit tests) | mock-store (default) / real (xfail) |
| 7. Dashboards & stats render | `tests/test_05_dashboards.py` | browser |
| 8. Teardown + pre-run sweep + clean assert | `tests/test_99_teardown.py` | browser + API |

### Email verification: two backends behind one interface

Email checks go through `mock_inbox.py`, which exposes two backends with the
same `wait_for_message(address, template_key=..., subject=...) -> InboxMessage`
interface plus `clear(address)` (teardown):

- **`MockInboxClient` (default).** A real HTTP client for the Datamailer
  **mock-inbox** API (#194, `datamailer` branch `issue-194-mock-inbox`). Sends
  to a *mock address* (`e2e+<tag>@mailbox.test`) are captured as
  `TransactionalMessage` rows instead of being delivered, and this client
  lists / fetches detail / clears them with retries + clear timeout errors.
  Contract (base URL = the Datamailer service root, `Bearer` client key):
  - `GET /api/mock-inbox/messages?address=<addr>&limit=25` → newest-first summaries
  - `GET /api/mock-inbox/messages/{id}` → `{message:{…, html_body, text_body, context, metadata}}`
  - `DELETE /api/mock-inbox/messages` `{address}` (or empty = clear all) → `{deleted_count}`
- **`RealInboxClient` (stub).** Placeholder for a real SES-inbound round-trip
  (#194 branch `issue-194-ses-inbound`). Its read contract isn't final, so it
  reports itself unconfigured and the tests that select it **xfail**. Exactly
  one test (`test_homework_confirmation_email_real_ses`, marked
  `@pytest.mark.real_inbox`) uses it via the `email_backend` selector.

**Backend selector.** The `email_backend` fixture resolves to `mock_inbox` by
default; a test marked `@pytest.mark.real_inbox` (or parametrized with `"real"`)
resolves to `real_inbox`. Most email assertions use the mock store; one uses
the real backend.

**What runs now vs. what's gated.** The client logic is covered by
`tests/test_06_mock_inbox_client.py` (17 unit tests, no network — paths, auth,
params, response shapes, poll/timeout, retries, disabled-deployment 404,
clear). The **live** email assertions in `test_03/04` need the mock inbox
**deployed to dev** with `MOCK_INBOX_ENABLED=1` and `E2E_MOCK_INBOX_*` creds
(it falls back to `DATAMAILER_URL` / `DATAMAILER_API_KEY`). When neither is set
they xfail; when set but the deployment has the mock inbox off, the endpoint
returns `404 mock_inbox_disabled` and the poll times out. The real-SES test
xfails until `issue-194-ses-inbound` and `E2E_REAL_INBOX_*` exist.

The student email is set to a unique per-run mock address
(`settings.mock_address(namespace)` → `e2e+<namespace>@mailbox.test`) and the
captured messages are cleared via the `DELETE` endpoint in each email test's
teardown.

### Teardown is best-effort by design (platform gap)

The API is read-only for submissions/enrollments/peer-reviews and has **no
course DELETE**. So teardown:

1. removes the student's project submission via the UI (the only remote way
   to delete a submission), then deletes the now-empty project;
2. closes + deletes homeworks/projects that have no submissions;
3. parks the leftover course (`visible=false`, renamed `[DELETED] ...`) since
   it cannot be deleted; the next run's **pre-run sweep** re-parks any stale
   `e2e-smoke-*` courses.

The post-run assertion verifies **no _visible_ `e2e-smoke-*` course remains**.
A separate `test_namespaced_course_fully_purged` is `xfail`ed with a TODO
referencing #194 — it will pass once the platform grows an admin/API delete
path for full cleanup.

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
| `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | browser flows | Staff account; logs in via the admin form (no OAuth). |
| `E2E_STUDENT_EMAIL` / `E2E_STUDENT_PASSWORD` | optional | If unset, a per-run `e2e+<namespace>@mailbox.test` mock-address student is created admin-side. |
| `E2E_MOCK_INBOX_URL` / `E2E_MOCK_INBOX_API_KEY` | email checks (mock) | Datamailer service root + client key. Fall back to `DATAMAILER_URL` / `DATAMAILER_API_KEY`. Email tests xfail when both unset. |
| `E2E_MOCK_INBOX_DOMAIN` / `E2E_MOCK_INBOX_TAG` | optional | Mock-address shape; default `mailbox.test` / `e2e`. Must match the datamailer `MOCK_INBOX_*` settings. |
| `E2E_REAL_INBOX_URL` / `E2E_REAL_INBOX_API_KEY` | email checks (real SES) | Not implemented yet (#194 `issue-194-ses-inbound`); real-backend test xfails. |
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
