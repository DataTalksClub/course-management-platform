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
mapfile -t containers < <(docker ps --format '{{.Names}}' | awk -v p="$prefix" 'index($0,p)==1')
evaluation=alarm
# Keep command output local and bounded. Only the parser's fixed categories and
# allowlisted alarm codes are ever sent to syslog or Relay.
diagnostic_dir=$(mktemp -d "${TMPDIR:-/tmp}/cmp-worker-check.XXXXXX")
trap 'rm -rf "$diagnostic_dir"' EXIT
diagnostic_category=no_container
diagnostic_alarms=()
# During a normal rolling release two containers may coexist. They share
# the same durable worker timestamps; a successful check on either is enough.
for container in "${containers[@]}"; do
  response="$diagnostic_dir/response"
  set +e
  timeout 45 docker exec "$container" python manage.py check_cmp_workers 2>/dev/null \
    | head -c 8193 >"$response"
  command_status=${PIPESTATUS[0]}
  set -e
  if (( command_status == 124 )); then
    diagnostic_category=timeout
    continue
  fi
  if (( command_status != 0 && command_status != 1 )); then
    diagnostic_category=check_failed
    continue
  fi

  # The worker command emits exactly {status, alarms}. Reject oversized,
  # malformed, inconsistent, or unknown responses without exposing their text.
  parsed=$(python3 - "$response" "$command_status" <<'PY'
import json
import sys

allowed_jobs = {"outbox", "health", "reminders", "digest", "scoring"}
allowed_codes = {
    *(f"{job}:{suffix}" for job in allowed_jobs for suffix in ("success_stale", "failed")),
    "outbox:backlog_age",
    "application_notifications:failed",
    "application_notifications:backlog_age",
    "scoring:stuck",
}

def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result

try:
    with open(sys.argv[1], "rb") as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError("oversized")
    payload = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    if not isinstance(payload, dict) or set(payload) != {"status", "alarms"}:
        raise ValueError("shape")
    alarms = payload["alarms"]
    if not isinstance(alarms, list) or len(alarms) > 16:
        raise ValueError("alarms")
    if any(not isinstance(code, str) or code not in allowed_codes for code in alarms):
        raise ValueError("code")
    if payload["status"] == "ok" and not alarms and sys.argv[2] == "0":
        print("ok")
    elif payload["status"] == "warning" and alarms and sys.argv[2] == "1":
        print("check_failed\t" + ",".join(sorted(set(alarms))))
    else:
        raise ValueError("status")
except Exception:
    print("invalid_response")
PY
  )
  if [[ "$parsed" == ok ]]; then
    evaluation=ok
    break
  elif [[ "$parsed" == invalid_response ]]; then
    diagnostic_category=invalid_response
  elif [[ "$parsed" == check_failed$'\t'* ]]; then
    diagnostic_category=check_failed
    codes=${parsed#*$'\t'}
    IFS=',' read -r -a parsed_codes <<< "$codes"
    diagnostic_alarms+=("${parsed_codes[@]}")
  else
    diagnostic_category=check_failed
  fi
done
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
  alarm_summary=$(printf '%s\n' "${diagnostic_alarms[@]}" | sort -u | head -n 16 | paste -sd, -)
  logger -t cmp-workers "CMP worker check failed category=${diagnostic_category} alarms=${alarm_summary:-none}"
  if [[ "$consecutive_fails" -ge "$fail_threshold" ]]; then
    status=alarm
  else
    status="${previous}"
  fi
fi
if [[ "$status" != "$previous" || ( "$status" == alarm && $((now-last)) -ge 3600 ) ]]; then
  echo "CMP_WORKERS_${status^^}"
  logger -t cmp-workers "CMP_WORKERS_${status^^}"
  if [[ "$status" == alarm || "$previous" == alarm ]]; then
    if [[ "$status" == alarm ]]; then
      alert_detail="category=${diagnostic_category}; alarms=${alarm_summary:-none}"
      relay_alert "$alert_to" "CMP workers $status" "CMP worker success or backlog age check: $status ($alert_detail)"
    else
      relay_alert "$alert_to" "CMP workers $status" "CMP worker success or backlog age check: $status"
    fi
  fi
  echo "$now" > "$state_dir/last-alert"
fi
echo "$status" > "$state_dir/status"
[[ "$status" == ok ]]
