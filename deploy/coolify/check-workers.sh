#!/bin/bash
# Independent watchdog. Never executes product work or shares its scheduler.
set -euo pipefail
if [[ -f /etc/cmp-worker-monitor.env ]]; then
  source /etc/cmp-worker-monitor.env
fi
prefix="${CMP_APP_PREFIX:-9gqubsq4lxubaxm27v1mtq9u-}"
state_dir="${CMP_MONITOR_STATE:-/var/lib/cmp-worker-monitor}"
mkdir -p "$state_dir"
exec 9>"$state_dir/lock"
flock -n 9 || exit 0
mapfile -t containers < <(docker ps --format '{{.Names}}' | awk -v p="$prefix" 'index($0,p)==1')
status=ok
if [[ ${#containers[@]} != 1 ]]; then
  status=alarm
elif ! timeout 45 docker exec "${containers[0]}" python manage.py check_cmp_workers >/dev/null 2>&1; then
  status=alarm
fi
previous=$(cat "$state_dir/status" 2>/dev/null || true)
last=$(cat "$state_dir/last-alert" 2>/dev/null || echo 0)
now=$(date +%s)
if [[ "$status" != "$previous" || ( "$status" == alarm && $((now-last)) -ge 3600 ) ]]; then
  echo "CMP_WORKERS_${status^^}"
  logger -t cmp-workers "CMP_WORKERS_${status^^}"
  # Existing host MTA owns credentials. Only fixed, payload-free messages leave host.
  if [[ "$status" == alarm || "$previous" == alarm ]]; then
    printf 'To: %s\nSubject: CMP workers %s\n\nCMP worker success or backlog age check: %s\n' \
      "${CMP_ALERT_TO:-dev@dtcdev.click}" "$status" "$status" | sendmail -t
  fi
  echo "$now" > "$state_dir/last-alert"
fi
echo "$status" > "$state_dir/status"
[[ "$status" == ok ]]
