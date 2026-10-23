# CMP Contabo recurring jobs P0 — t1265u

Date: 2026-10-23. Intake: 532fe08c-bc25-47ed-8880-922e86b29dd4.
Implementation commit: b1b7f4b99921a8e683ad44e7a94f895f76c21779.
Final scheduler/monitor definition: 88213bd (main).
Working directory: isolated detached worktree from origin/main, preserving the
original checkout's unrelated work. Pushed HEAD directly to main.

## Root cause and inventory

The architecture reviews missed Coolify's database-backed scheduled tasks.
Read-only live inventory at approximately 14:25 UTC found exactly three
production tasks, all targeting historical service cmp-staging (service 1):

| Job | Coolify task ID / UUID | Original cadence | Original last result |
| --- | --- | --- | --- |
| Outbox | 1 / 1uyereuryah2gkppequp4vjn | five minutes | success 14:20 UTC |
| Health | 2 / hhxzn2v587ml3a0tw87xbx79 | fifteen minutes | success 14:15 UTC |
| Daily reminders | 3 / qj3p3gksnxr74mvtqofqdm0k | 09:00 UTC | failed 09:00 UTC |

The reminder failure was missing Relay configuration in that service. The
production rolling application has effective Relay configuration. Empty
outbox runs appeared successful even with missing configuration. Source also
excluded abandoned PROCESSING work forever and failed to recheck retry due
time when claiming an event from an overlapping snapshot.

## Implementation

Final owner is the stable web container of cmp-staging (service 1,
avcfd5kwb7cj9r1tx4ygjs6v), running the same tested release as the public rolling
application. All three schedules specify container web and no application ID.
Outbox runs every minute, health every five minutes,
and daily reminders at 09:00 UTC. UTC is explicit in command execution and
verified in Coolify server settings. There is no second product scheduler or
additional worker container. Versioned reconciliation changes the existing
three task records; no deletion or replacement IDs.

Live activation exposed a Coolify constraint: application tasks refuse to run
while two rolling replicas coexist. The 14:41 application-targeted attempts
failed safely without execution; outbox resumed at 14:42. The final definition
therefore uses the stable service container, whose complete effective Relay
configuration was verified after redeployment. This prevents normal public
rolling overlap from blocking scheduled work.

Session advisory locks fence complete job execution and each outbox transport
call across processes and rolling replicas. Processing work older than 240
seconds becomes recoverable after process death; an expired timestamp cannot
steal a live session's lock. Retry claims recheck due time. Payload and downstream
idempotency keys are retained. Successful stable reminder audit keys are skipped.
Missing Relay configuration exits before queued rows are changed.

Persistent job timestamps and an independent host watchdog distinguish worker
success from web health. Success-age limits are 300 seconds for outbox, 900 for
health, and 26 hours for reminders. Due backlog older than 300 seconds and
processing older than 540 seconds alarm. Failure timestamps also alarm. Host
cron checks every minute, outside Coolify scheduling; it never executes work.
The existing host MTA carries fixed payload-free failure/recovery messages,
with one-hour repeat suppression.

## Backlog disposition before activation

Read-only production aggregates found 1,843 FAILED outbox rows: 1,818 single
membership upserts, 24 bulk upserts, and one homework-score notification. All
remain untouched. These are not an automatic retry queue; membership state
must be reconciled from current enrollment state, and score send intent must
be reviewed separately.

One abandoned bulk membership snapshot from August 27 was quarantined as DEAD
with an explicit disposition note. Its old snapshot could overwrite newer
membership state; it was not replayed or deleted. This quarantine preceded
activation of crash recovery. The 13 failed historical reminder audit records
were preserved, with no historical-window replay. Current reminder planning
returned zero events and zero members. Only normal current-window scheduling
is enabled; no blind reminder catch-up.

## Verification evidence

- Before implementation, focused tests failed because abandoned processing
  stayed processing and a not-yet-due retry dispatched. A separate focused
  test reproduced queued work being marked failed when Relay config was absent.
- After implementation, all nine focused tests passed on throwaway PostgreSQL.
  Independent database sessions proved live processing cannot be reclaimed even
  after its timestamp expires. Tests also cover retry recovery, overlapping
  snapshots, successful reminder deduplication, persistent success/failure, and
  controlled stale-success/backlog alarms.
- A real local HTTP server returned a transient Relay-style failure followed by
  success. Retry completed in 1.6 seconds with the same payload. A subprocess
  exited while owning an advisory lock; its abandoned row subsequently recovered.
- In a throwaway PostgreSQL database, controlled stale success and backlog age
  made the actual alarm command fail. The host watchdog's MTA seam captured an
  alarm, suppressed a repeated alarm, and captured recovery. No external email
  was sent during this controlled test.
- Django suite: 986 run, one skipped. Pytest: 775 passed, one skipped.
  Static type checks: zero errors. Migration drift and whitespace checks passed.

## Deployment and acceptance status

CI run 39970528080 completed successfully for the implementation commit.
Release: 20261023-143650-b1b7f4b. Isolated dev health reports this exact release;
database identity was confirmed as cmp_dev for both database and user, and the
initial dev outbox was empty. The deployed dev image passed the real HTTP
transient-failure/recovery drill in 1.58 seconds, killed-process recovery, and
controlled stale-success/backlog alarms. All three job success-age alarms
(outbox, health, reminders) and the last-failure alarm were additionally forced
and recovered in deployed dev. No real Relay delivery was attempted.

Production version metadata was stale before this work and was corrected to
the release tag in the service definition. Both public health endpoints and
the stable production runner now report the tested release. All three task
records are enabled with the documented final service owner.

Two fresh production membership rows were ACKED with a maximum creation-to-ack
latency of 2 minutes 26.98 seconds (last ACK 14:40:08 UTC). Further automatic
outbox runs succeeded at 14:42 and 14:43 UTC. At 14:43:30 UTC active backlog
was zero and all worker alarms were clear. A safe current-window reminder run
at 14:40:29 UTC produced zero events and persisted success; daily scheduling
remains 09:00 UTC, with no historical replay.

The independent host watchdog and minutely cron are installed on contabo-a.
Its initial run returned CMP_WORKERS_OK and persisted healthy state. It uses
the existing host MTA without changing credentials. The final automatic health
run started at 14:45:04 UTC and succeeded at 14:45:08 UTC. Automatic outbox
runs also succeeded at 14:43:05, 14:44:06 and 14:45:07 UTC. At 14:45:18 UTC
all three job success timestamps were fresh, active backlog was zero, and the
actual production alarm command returned no alarms. The independent watchdog
also returned success and its persistent state was healthy.

## Acceptance coverage

1. Exactly three enabled Coolify tasks, IDs 1, 2 and 3, target the one stable
   production service web container; no application target or duplicate task.
   Final database inventory and versioned reconciliation agree.
2. Fresh production outbox rows progressed within 147 seconds; automatic
   minutely cadence was observed. Health succeeded on its five-minute cadence,
   within the fifteen-minute requirement. Reminders explicitly run 09:00 UTC.
3. PostgreSQL overlap fencing, a killed process, real transient HTTP failure,
   stable payload retry, and successful-reminder deduplication were verified.
4. Historical failures and overdue reminders were reviewed before activation,
   preserved without replay, and the one stale bulk snapshot was quarantined.
   No AWS schedule was enabled or otherwise changed; same-day disabled-state
   evidence and the fresh-read access limitation are recorded below.
5. Success-age alarms for every job, last-failure and backlog alarms fired and
   recovered in non-production; watchdog notification/deduplication/recovery
   was captured locally. The independent watchdog is active and healthy.
   Implementation and operational definitions were pushed directly to main;
   this sanitized report is also copied into the repository.

Old AWS schedules: the same-day architecture reviews recorded all three old
production rules as DISABLED. This implementation makes no AWS changes and
never enables them. A fresh read through the required investigator profile
was denied because AWS Gate was closed; the user was asked to open it. No
broader credential fallback was used.

No Cloudflare or DNS mutations, secret deletions, resource deletions, queue
purges, historical reminder sends, screenshots, or private payload publication.
