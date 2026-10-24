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
alert_from="${CMP_ALERT_FROM:-alerts@dtcdev.click}"
alert_from_name="${CMP_ALERT_FROM_NAME:-DTC Alerts}"
alert_msmtp_account="${CMP_ALERT_MSMTP_ACCOUNT:-alerts}"
mkdir -p "$state_dir"
exec 9>"$state_dir/lock"
flock -n 9 || exit 0
mapfile -t containers < <(docker ps --format '{{.Names}}' | awk -v p="$prefix" 'index($0,p)==1')
status=alarm
# During a normal rolling release two containers may coexist. They share
# the same durable worker timestamps; a successful check on either is enough.
for container in "${containers[@]}"; do
  if timeout 45 docker exec "$container" python manage.py check_cmp_workers >/dev/null 2>&1; then
    status=ok
    break
  fi
done
previous=$(cat "$state_dir/status" 2>/dev/null || true)
last=$(cat "$state_dir/last-alert" 2>/dev/null || echo 0)
now=$(date +%s)
if [[ "$status" != "$previous" || ( "$status" == alarm && $((now-last)) -ge 3600 ) ]]; then
  echo "CMP_WORKERS_${status^^}"
  logger -t cmp-workers "CMP_WORKERS_${status^^}"
  # Existing host MTA owns credentials. Only fixed, payload-free messages leave host.
  if [[ "$status" == alarm || "$previous" == alarm ]]; then
    raw_from="$alert_from"
    from_pat='<([^>]+)>'
    if [[ "$alert_from" =~ $from_pat ]]; then
      raw_from="${BASH_REMATCH[1]}"
    fi
    if [[ "$alert_from" == *"<"*">"* ]]; then
      from_header="$alert_from"
    elif [[ -n "${alert_from_name:-}" ]]; then
      from_header="${alert_from_name} <${raw_from}>"
    else
      from_header="$raw_from"
    fi

    send_cmd=()
    msmtp_bin="$(command -v msmtp 2>/dev/null || true)"
    sendmail_bin="$(command -v sendmail 2>/dev/null || true)"
    if [[ -z "$sendmail_bin" && -x /usr/sbin/sendmail ]]; then
      sendmail_bin="/usr/sbin/sendmail"
    fi

    if [[ -n "$msmtp_bin" && -x "$msmtp_bin" ]]; then
      send_cmd=("$msmtp_bin")
      if [[ -n "${alert_msmtp_account:-}" ]]; then
        send_cmd+=(-a "$alert_msmtp_account")
      fi
      send_cmd+=(-f "$raw_from" -t)
    elif [[ -n "$sendmail_bin" && -x "$sendmail_bin" ]]; then
      send_cmd=("$sendmail_bin")
      target="$(readlink -f "$sendmail_bin" 2>/dev/null || true)"
      if [[ "$target" == *"msmtp"* && -n "${alert_msmtp_account:-}" ]]; then
        send_cmd+=(-a "$alert_msmtp_account")
      fi
      send_cmd+=(-f "$raw_from" -t)
    fi

    if [[ ${#send_cmd[@]} -gt 0 ]]; then
      printf 'From: %s\nTo: %s\nSubject: CMP workers %s\n\nCMP worker success or backlog age check: %s\n' \
        "$from_header" "$alert_to" "$status" "$status" | "${send_cmd[@]}"
    fi
  fi
  echo "$now" > "$state_dir/last-alert"
fi
echo "$status" > "$state_dir/status"
[[ "$status" == ok ]]
