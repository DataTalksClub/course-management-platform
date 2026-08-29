---
name: verify
description: Run this Django app locally against a throwaway database and drive its pages over HTTP to observe a change working. Use when verifying student/cadmin page behavior end-to-end.
---

# Verifying changes in this app

Django server-rendered app. The surface is HTTP + rendered HTML, so verify by
running the server and fetching pages — not by running the test suite.

## Throwaway database (never touch the dev db)

`DATABASE_URL` overrides the default `sqlite:///db/db.sqlite3`. Point it at a
scratch file so seeding doesn't mutate the real dev data:

```bash
export DATABASE_URL="sqlite:///$SCRATCH/verify.sqlite3"
uv run python manage.py migrate
uv run python manage.py shell < seed.py     # create Course/Homework/Question
uv run python manage.py runserver 8971 --noreload
```

Health check to confirm it's up: `curl http://127.0.0.1:8971/api/health/`

## URL shapes

Homework pages are `/<course_slug>/homework/<homework_slug>` — **no `/course/`
prefix and no trailing slash**. Check `courses/urls.py` before guessing; a wrong
path returns a 404 page that greps as "no output" and looks like a failed feature.

## Authenticating in a browser

Login is **allauth OAuth only** — there is no username/password form to fill, so
Playwright can't log in through the UI. Mint a session cookie instead:

```python
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
s = SessionStore()
s[SESSION_KEY] = str(user.pk)
s[BACKEND_SESSION_KEY] = "allauth.account.auth_backends.AuthenticationBackend"
s[HASH_SESSION_KEY] = user.get_session_auth_hash()
s.create()
```

`ModelBackend` is commented out in `AUTHENTICATION_BACKENDS` — using it makes the
session silently unauthenticated. Then `ctx.add_cookies([{"name": "sessionid",
"value": key, "domain": "127.0.0.1", "path": "/"}])`.

## Gotchas

- Homework/project open-vs-closed is driven by `state` (OPEN/CLOSED/SCORED),
  **not** by `due_date`. A passed deadline alone does not close a form.
- Submitting a homework URL performs a **real network check** on the repo. Use a
  genuine public repo (e.g. `https://github.com/DataTalksClub/llm-zoomcamp`);
  fake URLs are rejected with "does not exist".
- "Deadline passed" / time-left text is rendered client-side by
  `courses/static/time_left.js`, so it will not appear in `curl` output — use a
  browser to see it.
- Badges use `app-badge-upper` (CSS uppercase), so Playwright `inner_text()`
  returns "NOT SUBMITTED" while the template source says "Not submitted".
- Playwright + chromium are already installed (`uv run python`, `~/.cache/ms-playwright`).
