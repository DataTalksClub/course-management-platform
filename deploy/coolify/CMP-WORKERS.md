# CMP production recurring work

Owner: CMP maintainers; host monitor: machine-management operators. Exactly one
Coolify scheduled task owns each job on contabo-a. All target application
`cmp-production-rolling-web` (`9gqubsq4lxubaxm27v1mtq9u`), so they follow the
current immutable app image and its Relay configuration. PostgreSQL session
advisory locks fence overlaps across replicas and releases. No worker container
or additional host scheduler executes these jobs.

| Job | Coolify task UUID | Command | Cadence |
| --- | --- | --- | --- |
| outbox | 1uyereuryah2gkppequp4vjn | python manage.py run_cmp_job outbox | every minute |
| health | hhxzn2v587ml3a0tw87xbx79 | python manage.py run_cmp_job health | every five minutes |
| reminders | qj3p3gksnxr74mvtqofqdm0k | python manage.py run_cmp_job reminders | daily 09:00 UTC |

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

`reconcile-cmp-workers.php` is the idempotent schedule definition. Copy it into
the Coolify container, run `php` on the file for a dry run, and add `--apply`
after verifying the image and database migration. It moves existing schedules;
it never creates a second owner. Do not enable old AWS rules.

The web entrypoint remains the migration owner. Scheduled commands never
migrate. For failover, fence the old application before activating a replacement
against the promoted database. Do not activate AWS schedules for failover.

The independent host watchdog `check-workers.sh` runs from `cmp-workers.cron`
every minute, outside Coolify's scheduler. It resolves running containers of the rolling application, tolerates normal
release overlap, runs `check_cmp_workers`, and alerts through the existing host MTA.
Payload-free alarms cover missing/stale success (outbox 300s, health 900s,
reminders 26h), failed last attempts, due backlog older than 300s, and processing
older than 540s. State under `/var/lib/cmp-worker-monitor` deduplicates mail for
one hour; recovery sends once. The monitor never runs jobs. Configure overrides
in root-only `/etc/cmp-worker-monitor.env` if the rolling application changes.

Recovery: restore the runner/image/configuration, inspect alarm output locally,
verify new success timestamps and oldest-due age, and require monitor recovery.
Do not mute alerts, truncate queues, or reset old reminder windows.
