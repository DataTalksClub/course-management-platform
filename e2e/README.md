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
| 6. Email verification (homework + project confirmation emails) | `tests/test_03/04` (`@pytest.mark.email`) | **stub / xfail** |
| 7. Dashboards & stats render | `tests/test_05_dashboards.py` | browser |
| 8. Teardown + pre-run sweep + clean assert | `tests/test_99_teardown.py` | browser + API |

### Email verification is stubbed (on purpose)

The Datamailer **mock-inbox** endpoint (a separate #194 sub-task owned by the
`datamailer/` repo) is not final. The email checks are written against a small
`MockInboxClient.wait_for_message(address, subject=...)` abstraction
(`mock_inbox.py`) and **xfail** until `E2E_MOCK_INBOX_URL` is set. Update the
proposed contract in `mock_inbox.py` and set the env var to turn them on.

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
| `E2E_STUDENT_EMAIL` / `E2E_STUDENT_PASSWORD` | optional | If unset, a per-run `<namespace>@inbox.dtcdev.click` student is created admin-side. |
| `E2E_MOCK_INBOX_URL` / `E2E_MOCK_INBOX_API_KEY` | email checks | Leave unset until the mock inbox lands (#194); email tests xfail. |
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
