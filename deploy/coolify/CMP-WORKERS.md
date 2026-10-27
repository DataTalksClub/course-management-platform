# CMP production recurring work

Owner: CMP maintainers; host monitor: machine-management operators. Exactly one
Coolify scheduled task owns each job on contabo-a. All target the stable `web` container of service
`cmp-staging` (`avcfd5kwb7cj9r1tx4ygjs6v`), using the current immutable app
image and verified Relay configuration. The public rolling web application is
not a scheduler target: Coolify rejects scheduled application tasks while two
replicas overlap. PostgreSQL session
advisory locks fence overlaps across replicas and releases. No worker container
or additional host scheduler executes these jobs.

| Job | Coolify task UUID | Command | Cadence |
| --- | --- | --- | --- |
| outbox | 1uyereuryah2gkppequp4vjn | python manage.py run_cmp_job outbox | every minute |
| health | hhxzn2v587ml3a0tw87xbx79 | python manage.py run_cmp_job health | every five minutes |
| reminders | qj3p3gksnxr74mvtqofqdm0k | python manage.py run_cmp_job reminders | daily 09:00 UTC |
| scoring | — (always-on `worker` service) | python manage.py run_cmp_job scoring | continuous loop, 5s interval |
| digest | — (piggybacked on outbox) | maybe_send_scheduled_digest() inside process_datamailer_outbox | once per Europe/Berlin day after 09:00 Berlin |

The digest needs no Coolify task: the minutely outbox tick in the stable
container sends at most one digest per Europe/Berlin date (07:00 UTC in
summer CEST, 08:00 UTC in winter CET — "around 09:00 Berlin" both ways),
covering the previous 24h of registrations grouped by course. One
`RegistrationDigestSend` row per Berlin date plus stable per-date Relay
idempotency keys make it idempotent across restarts and rolling overlap.
Zero registrations in the window means no email (a `skipped_empty` row is
recorded). Digest failures never block the outbox; they retry on the next
minute tick. Manual trigger: `python manage.py send_registration_digest`
(`--dry-run` prints without sending; `--force` resends with the same keys).

Business timezone is explicitly UTC, including reminder selection; no DST
shift. Coolify server timezone must remain UTC. A failed or missed reminder
run is alerted, never automatically replayed with an old `--now` value.
Successful stable reminder keys are skipped locally; ambiguous crash outcomes
retry with the same Relay member idempotency keys. Relay owns durable mail
transport, not CMP recipient selection.

Outbox retries preserve payloads and downstream idempotency keys. After a crash,
processing rows older than 240 seconds are eligible again. The per-event session
lock remains held throughout transport, so a slow live process cannot be
reclaimed by another runner. Process death releases that database lock.
Missing Relay configuration fails the command before changing queued work.
Do not reset FAILED/DEAD rows automatically. Review stale recipient snapshots
against current enrollment state and review score publications for intended
send semantics. Rebuild current sync work rather than replaying stale snapshots.

Historical reminder audit failures are evidence, not a replay queue. Inspect
current deadline windows using `send_deadline_reminders --dry-run`; never pass
historical `--now` values in production as a catch-up shortcut. Preserve audit
and failed rows for owner disposition.

Bulk member upserts and transient reminder sends share a per-client pace of
one request start per 1.25 seconds (at most 240 starts per five minutes),
leaving headroom under Relay's 300/5m per-IP edge limit. Bodies remain below
7 KiB. The reminder schedule timeout is 1800 seconds; the other jobs retain
300 seconds. A large reminder run can legitimately take over ten minutes.
Partial sends retain the same per-member idempotency keys on recovery; inspect
the current window before retrying. Do not change keys or replay old windows.

`reconcile-cmp-workers.php` is the idempotent schedule definition. Copy it into
the Coolify container, run `php` on the file for a dry run, and add `--apply`
after verifying the image and database migration. It moves existing schedules;
it never creates a second owner. Do not enable old AWS rules.

The web entrypoint remains the migration owner. Scheduled commands never
migrate. For failover, fence the old application before activating a replacement
against the promoted database. Do not activate AWS schedules for failover.

The independent host watchdog `check-workers.sh` runs from `cmp-workers.cron`
every minute, outside Coolify's scheduler. It resolves the stable service runner container, runs `check_cmp_workers`, and alerts through the existing host MTA.
Payload-free alarms cover missing/stale success (outbox 300s, health 900s,
reminders 26h, digest 26h, scoring 600s), failed last attempts, due backlog older than 300s, processing
older than 540s (scoring backlog older than 600s, stuck scoring processing
older than 1800s), and application-notification failures. State under `/var/lib/cmp-worker-monitor` enforces hysteresis
via `CMP_FAIL_THRESHOLD` (default 2 consecutive failing evaluations 60s apart)
to avoid false alarms during container replacement or rolling restarts.
Two minute-spaced evaluations add up to 120s after a breach, plus check time
(45s timeout for the single stable runner). Detection bounds, including that
timeout, are outbox/backlog 465s, health 1065s, and reminders 26h+165s from
last success/due time. Email transport latency is additional. It deduplicates mail
for one hour; recovery sends once. The monitor never runs jobs. Configure overrides
in root-only `/etc/cmp-worker-monitor.env` if the service runner or thresholds change.

Recovery: restore the runner/image/configuration, inspect alarm output locally,
verify new success timestamps and oldest-due age, and require monitor recovery.
Do not mute alerts, truncate queues, or reset old reminder windows.

## Scoring worker

Homework/project scoring and peer-review assignment never run inside the web
request: the API (`.../score/`, `.../assign-reviews/`) and cadmin actions
enqueue a `ScoringJob` row and return immediately (API: HTTP 202 with
`job_id` and `poll_url`; cadmin: "queued" message). The same paths serve GET
for job status (`queued`/`processing`/`succeeded`/`failed`).

Execution owns the `worker` service in `docker-compose.dev.yml`,
`docker-compose.staging.yml`, and local `docker-compose.yml`:
`python manage.py run_scoring_worker` drains the queue every 5 seconds,
`restart: unless-stopped`, healthcheck on the `/tmp/scoring-worker-heartbeat`
file (stale after 90s). The image pins (`web.image`, `worker.image`,
`VERSION`) must move together; the GHA pin step and `hetzner-rollout.sh`
replace the image in every service, and the deploy verify selects the `web`
application by name.

Fallback: `python manage.py run_cmp_job scoring` processes up to 25 pending
jobs (Coolify scheduled-task compatible, singleton via `worker_lock`).
`check_cmp_workers` alarms on stale scoring success (600s), scoring backlog
older than 600s, and stuck scoring processing older than 1800s.

Idempotency: duplicate POSTs while a job is active return the existing job
instead of a new row; the worker claims jobs with row locking and a 10-minute
stale reclaim, serializes per target with `worker_lock`, and re-checks the
terminal state (SC/CO, existing peer reviews) before running, so a retry
after a crash marks "already scored (idempotent skip)" instead of
double-scoring. Scoring itself runs in one atomic transaction.
