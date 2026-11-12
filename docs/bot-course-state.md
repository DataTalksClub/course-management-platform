# Read-only bot course state

`GET /api/bot/courses/<exact-cohort-slug>/state/` accepts only
`Authorization: Bearer <CMP_BOT_READ_TOKEN>`. Set a separate random token in
Coolify's web service environment and in the bot's secret configuration. This
capability does not authenticate to staff CRUD/action APIs. Empty configuration
fails closed. Responses are private and must not be cached.

The version-1 response contains `fetched_at`, `course`, `homeworks`, `projects`,
and `student`. Public objects include titles, slugs, source URLs, states and
stored dates. States are enum names (`OPEN`, `PEER_REVIEWING`, etc.).
`peer_review_open` reflects the actual project state. `assignments_created`
reports whether any review assignments exist for the project. It is independent
of whether reviewing is currently open. No submission, grade, student name or
review target is returned.

CMP has no scheduled peer-review opening timestamp: `peer_review_opens_at` is
always null. A submission deadline or project start time must never be presented
as a promised review opening time. Use an explicit cohort slug in the bot
configuration; do not infer the cohort from the calendar year.

Optional `slack_team_id` and `slack_user_id` query parameters must be supplied
together. An exact linked allauth Slack account (`provider=slack`,
`uid=TEAM_USER`) for an active user yields `student.mapped=true` and that user's
per-project `assigned_count` and `pending_count`. Missing links yield
`mapped=false`, never guessed email/name matches or a fabricated zero count.

The bot must whitelist the public fields before injecting context into an LLM
that answers a channel. Personal `student` data belongs in an ephemeral reply or
DM to the authenticated asking Slack user only; exclude it entirely from the
public prompt, public answer, logs and citations. Reaction-triggered requests
must not infer that the reacting administrator is the original student's identity.

The endpoint accepts GET only and never writes to CMP. Invalid credentials yield
401, malformed partial Slack identities 400, and unknown/hidden courses 404.
Consumers should use a bounded timeout, alert the operator on failure, and fall
back to their normal answer flow.
