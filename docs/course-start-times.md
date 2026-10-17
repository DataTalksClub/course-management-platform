# Course and assignment start times

CMP stores optional `starts_at` on Course, Homework and Project. These fields
describe timing; they do not open submissions or send announcements. CMP has no
module or self-paced delivery model. The website owns module start times,
cohort delivery mode and announcement scheduling. Only live cohorts are
eligible for that scheduling; self-paced content must not generate schedules.

`starts_at` accepts an offset-aware ISO8601 timestamp or JSON `null`. API writes
normalize to UTC. Naive timestamps and date-only values are rejected. An
assignment's start must be at or before its submission deadline (and project
peer-review deadline). A course's start must fall on or before `end_date` in
UTC; the entire UTC end day is allowed because this boundary has date precision.
Model `clean()` applies the same validation. As with other Django model
validation, direct ORM callers must call `full_clean()` before saving.

Migration 0045 initializes a known Course `start_date` to midnight UTC. This
is a deterministic date-resolution convention, **not evidence of a historical
launch hour**. Missing boundaries and invalid legacy date ranges remain null.
Homework/project starts remain null: CMP has no reliable module-start boundary
from which to backfill them. No value is inferred by subtracting time from a
deadline, and no migration creates announcement schedules. Re-running the
backfill preserves existing explicit values.

Existing `start_date` remains a public date field. Updating it does not silently
move `starts_at`, and updating a deadline does not move a start. For a reschedule,
send all intended timing changes together. Clearing `starts_at` restores unknown
timing; it never falls back to an assignment deadline.

## Authenticated API

Existing course, homework and project list/detail responses include `starts_at`,
including the assignment summaries embedded in course detail. Writes use the
existing staff Token authentication and routes:

- `POST /api/courses/`, `PATCH /api/courses/<course_slug>/`
- `POST /api/courses/<course_slug>/homeworks/` or `projects/`
- `PUT` (upsert) or `PATCH /api/courses/<course_slug>/homeworks/by-slug/<slug>/`
- `PUT` (upsert) or `PATCH /api/courses/<course_slug>/projects/by-slug/<slug>/`
- Existing numeric assignment detail PATCH routes also accept `starts_at`.

For example, PATCH `{"starts_at":"2026-11-02T09:00:00+01:00"}` or
`{"starts_at":null}`. Omission preserves the current value. Validation considers
the complete resulting object, including when only a deadline changes.

## CLI

The management command uses these same HTTP endpoints and token permissions.
Set `AUTH_TOKEN` in the environment (never pass tokens in command arguments).
Use `--token-env NAME` to select another variable. Reads use GET; supplying
timing changes uses PATCH. Remote origins require HTTPS; redirects are disabled.

```bash
uv run python manage.py course_timing ml-2026 --base-url https://dev.courses.datatalks.club
uv run python manage.py course_timing ml-2026 --base-url https://dev.courses.datatalks.club --starts-at 2026-11-02T08:00:00Z --start-date 2026-11-02
uv run python manage.py course_timing ml-2026 --base-url https://dev.courses.datatalks.club --homework module-1 --starts-at 2026-11-02T08:00:00Z --due-date 2026-11-09T08:00:00Z
uv run python manage.py course_timing ml-2026 --base-url https://dev.courses.datatalks.club --project final --clear-start
```

Course options include `--start-date`/`--end-date`; homework uses `--due-date`;
project uses `--submission-due-date`/`--peer-review-due-date`. The API remains
the validation owner. The command does not access the local database.

## Website import contract

The existing website SQLite import at
`courses/services/cmp_content_import.py` consumes these additive columns on
`courses_course`, `courses_homework`, and `courses_project`. API consumers use
the same nullable ISO8601 property. Old source schemas without the column remain
supported by the website import. The website worker owns that implementation.

An explicit nonnull upstream start may initialize an untouched website timing
row (`timing_revision=0`). Missing/null inputs do not invent values or erase
local timing. Local website timing edits, including an explicit clear, increment
the revision and survive later imports. Module/placement propagation must use
an explicit terminal-homework relationship, never title or guessed ordering.
There is no second CMP scheduler, cross-service queue or automatic live sync.
