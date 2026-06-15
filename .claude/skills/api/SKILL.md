---
name: api
description: How to reach the platform REST API — where prod and dev live, where the API token is (.env), how to authenticate with curl, and how to fetch the OpenAPI spec listing every endpoint. Use whenever you need to read or edit course/homework/project/registration data, or inspect real prod data while debugging.
---

# Platform REST API (`/api/`)

Everything the platform exposes for courses, homeworks, projects, questions, and
registration campaigns is available as JSON under `/api/`. This skill tells you
how to connect and how to discover the endpoints; the live OpenAPI spec is the
source of truth for the exact routes and payloads.

## Where things live

| Instance | Base URL | Token (in `.env`) |
|----------|----------|-------------------|
| Production | `https://courses.datatalks.club` | `AUTH_TOKEN` |
| Dev | `https://dev.courses.datatalks.club` | `DEV_AUTH_TOKEN` |

Default to **dev** when experimenting. Use prod read-only unless you explicitly
intend to change production data.

## The API token

Tokens are DRF-style `Token`s stored in each instance's own database, so a prod
token works only on prod and a dev token only on dev. Both are kept in the
project's `.env` file (not exported as shell vars), as `AUTH_TOKEN` and
`DEV_AUTH_TOKEN`.

Read the right token out of `.env` without printing it:

```bash
# prod
TOKEN=$(grep -E '^AUTH_TOKEN=' .env | cut -d= -f2- | tr -d '"'\'' \r')
# dev
TOKEN=$(grep -E '^DEV_AUTH_TOKEN=' .env | cut -d= -f2- | tr -d '"'\'' \r')
```

## Authenticate

Every endpoint except `/api/health/` needs this header:

```
Authorization: Token <key>
```

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "https://dev.courses.datatalks.club/api/courses/" | python3 -m json.tool
```

Write actions (score, delete, some edits) additionally require the token's user
to be **staff**, otherwise you get `403 staff_token_required`.

Health / deployed version (no auth — handy to confirm which commit is live):

```bash
curl -s https://courses.datatalks.club/api/health/
# {"status": "ok", "version": "20260606-083515-7c464aa"}
```

## Discover all endpoints (OpenAPI)

The spec is generated from the routes and models, so it is always current. Fetch
it instead of guessing routes:

```bash
# Full spec
curl -s -H "Authorization: Token $TOKEN" \
  "https://dev.courses.datatalks.club/api/openapi.json" | python3 -m json.tool

# Just the list of paths + methods
curl -s -H "Authorization: Token $TOKEN" \
  "https://dev.courses.datatalks.club/api/openapi.json" \
  | python3 -c 'import sys,json;
d=json.load(sys.stdin);
[print(m.upper().ljust(7), p) for p,ms in d["paths"].items() for m in ms]'
```

## Example: inspect a homework (e.g. when debugging a prod issue)

```bash
TOKEN=$(grep -E '^AUTH_TOKEN=' .env | cut -d= -f2- | tr -d '"'\'' \r')

# Homework config: state (OP/CL/SC), enabled fields, counts. Note the numeric id.
curl -s -H "Authorization: Token $TOKEN" \
  "https://courses.datatalks.club/api/courses/<course_slug>/homeworks/by-slug/<hw_slug>/" \
  | python3 -m json.tool

# Its questions: types, options, correct answers (uses the id from above)
curl -s -H "Authorization: Token $TOKEN" \
  "https://courses.datatalks.club/api/courses/<course_slug>/homeworks/<hw_id>/questions/" \
  | python3 -m json.tool
```

## Where the code is

- Routes: `api/urls.py`
- Views: `api/views/`
- OpenAPI generator: `api/openapi.py`
