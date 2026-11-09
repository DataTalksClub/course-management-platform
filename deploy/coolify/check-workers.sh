#!/bin/bash
# Independent watchdog. Never executes product work or shares its scheduler.
set -euo pipefail
if [[ -f /etc/cmp-worker-monitor.env ]]; then
  # shellcheck source=/dev/null
  source /etc/cmp-worker-monitor.env
fi
prefix="${CMP_APP_PREFIX:-web-avcfd5kwb7cj9r1tx4ygjs6v}"
state_dir="${CMP_MONITOR_STATE:-/var/lib/cmp-worker-monitor}"
alert_to="${CMP_ALERT_TO:-dev@dtcdev.click}"
fail_threshold="${CMP_FAIL_THRESHOLD:-2}"

# One client/key for Contabo monitors, stored root-owned mode 0600. The CLI
# loads it from disk; credentials never appear in process arguments or logs.
relay_alert() {
  local recipients="${1// /,}" subject="$2" body="$3" recipient sent=0
  local -a addresses=()
  IFS=',' read -r -a addresses <<< "$recipients"
  for recipient in "${addresses[@]}"; do
    [[ -n "$recipient" ]] || continue
    if ! printf '%s\n' "$body" | env -u DATAMAILER_API_KEY -u DATAMAILER_URL \
      DATAMAILER_CONFIG="${RELAY_MONITOR_CONFIG:-/etc/relay-monitors.toml}" \
      "${DATAMAILER_BIN:-/usr/local/bin/datamailer}" send --from alerts \
      --to "$recipient" --subject "$subject"; then
      echo "ERROR: Relay alert delivery request failed" >&2
      return 1
    fi
    sent=$((sent + 1))
  done
  [[ "$sent" -gt 0 ]]
}

# Exercise this source's real transport without queries, repairs or state changes.
# The proof destination is fixed, irrespective of the configured recipients.
if [[ "${1:-}" == "--test-alert" ]]; then
  relay_alert dev@dtcdev.click "TEST cmp-check-workers Relay alert" "Controlled cmp-check-workers alert transport proof."
  exit $?
fi
mkdir -p "$state_dir"
exec 9>"$state_dir/lock"
flock -n 9 || exit 0
# Never forward raw command output: exceptions may contain credentials or PII.
# The host needs Python 3 only to parse JSON and allowlist diagnostic labels.
safe_alarm_labels() {
  python3 -c '
import json, sys
jobs = ("outbox", "health", "reminders", "digest", "scoring")
allowed = {f"{job}:{kind}" for job in jobs for kind in ("success_stale", "failed")}
allowed.update(("outbox:backlog_age", "application_notifications:failed",
                "application_notifications:backlog_age", "scoring:backlog_age", "scoring:stuck"))
labels = set()
for line in sys.stdin:
    try:
        payload = json.loads(line)
    except ValueError:
        continue
    if isinstance(payload, dict) and isinstance(payload.get("alarms"), list):
        labels.update(label for label in payload["alarms"]
                      if isinstance(label, str) and label in allowed)
print(",".join(sorted(labels)) or "unavailable")
'
}

evaluation=alarm
details=no_runner
containers=()
if container_names=$(docker ps --format '{{.Names}}' 2>/dev/null); then
  mapfile -t containers < <(printf '%s\n' "$container_names" | awk -v p="$prefix" 'index($0,p)==1')
else
  details=container_discovery_failed
fi
# During a normal rolling release two containers may coexist. They share
# the same durable worker timestamps; a successful check on either is enough.
for container in "${containers[@]}"; do
  if check_output=$(timeout 45 docker exec "$container" python manage.py check_cmp_workers 2>&1); then
    evaluation=ok
    details='check_exit=0 alarms=none'
    break
  else
    check_exit=$?
    labels=$(printf '%s\n' "$check_output" | safe_alarm_labels 2>/dev/null) || labels=unavailable
    # Preserve failures from each replica without exposing names or raw output.
    if [[ "$details" == no_runner ]]; then details=""; fi
    details+="check_exit=${check_exit} alarms=${labels}; "
  fi
done
unset check_output container_names
checked_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
evidence="checked_at=${checked_at} result=${evaluation} ${details}"
printf '%s\n' "$evidence" > "$state_dir/last-check"
previous=$(cat "$state_dir/status" 2>/dev/null || echo "ok")
consecutive_fails=$(cat "$state_dir/consecutive-failures" 2>/dev/null || echo 0)
last=$(cat "$state_dir/last-alert" 2>/dev/null || echo 0)
now=$(date +%s)

if [[ "$evaluation" == "ok" ]]; then
  if [[ "$consecutive_fails" -gt 0 && "$previous" != "alarm" ]]; then
    logger -t cmp-workers "CMP worker check recovered before alarm threshold (after ${consecutive_fails} transient failure(s))"
  fi
  consecutive_fails=0
  echo "0" > "$state_dir/consecutive-failures"
  status=ok
else
  consecutive_fails=$((consecutive_fails + 1))
  echo "$consecutive_fails" > "$state_dir/consecutive-failures"
  logger -t cmp-workers "CMP worker check evaluation failed (evaluation ${consecutive_fails} of ${fail_threshold}): ${evidence}"
  if [[ "$consecutive_fails" -ge "$fail_threshold" ]]; then
    status=alarm
  else
    status="${previous}"
  fi
fi
if [[ "$status" != "$previous" || ( "$status" == alarm && $((now-last)) -ge 3600 ) ]]; then
  echo "CMP_WORKERS_${status^^}"
  logger -t cmp-workers "CMP_WORKERS_${status^^} ${evidence}"
  if [[ "$status" == alarm || "$previous" == alarm ]]; then
    relay_alert "$alert_to" "CMP workers $status" "CMP worker success or backlog age check: $status; $evidence"
  fi
  echo "$now" > "$state_dir/last-alert"
fi
echo "$status" > "$state_dir/status"
[[ "$status" == ok ]]
