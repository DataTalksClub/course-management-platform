#!/usr/bin/env bash
# cmp-created-watchdog — self-heal Coolify-managed containers stuck in Created.
#
# Incident t658u (2026-10-22): Coolify deploy of cmp-staging
# (service avcfd5kwb7cj9r1tx4ygjs6v, GHA run 39806180586) pulled the new image,
# stopped the old container, created the replacement, but never started it.
# Traefik returned 503 for courses.datatalks.club until a manual
# `docker start` ~3 min later. The 5-min HTTP healthcheck missed the window.
#
# This watchdog runs every 2 min on contabo-a (contabo) and starts any
# coolify-managed container that has been sitting in Created beyond a grace
# period. HTTP alerting stays with the existing coolify-healthcheck
# (every 5 min, dev@dtcdev.click) — this script only pages on its own
# heal actions, so there is no duplicate alerting.
#
# Install (contabo-a, as root):
#   install -m 755 deploy/coolify/cmp-created-watchdog.sh /usr/local/sbin/cmp-created-watchdog.sh
#   printf '%s\n' '*/2 * * * * root /usr/bin/flock -n /var/lock/cmp-created-watchdog.lock /usr/local/sbin/cmp-created-watchdog.sh >> /var/log/cmp-created-watchdog.log 2>&1' \
#     > /etc/cron.d/cmp-created-watchdog
#   DRY_RUN=1 /usr/local/sbin/cmp-created-watchdog.sh   # no-op smoke test
#
# Env overrides (all optional):
#   GRACE_SEC=120            # ignore freshly created containers (deploy in progress)
#   STATE_DIR=/var/lib/cmp-created-watchdog
#   ALERT_TO=dev@dtcdev.click
#   ALERT_REPEAT_MIN=60       # dedupe heal alerts per container
#   DRY_RUN=1                 # log what would be started, do not start/mail
set -euo pipefail

if [[ -f /etc/cmp-created-watchdog.env ]]; then
  # shellcheck source=/dev/null
  source /etc/cmp-created-watchdog.env
fi

GRACE_SEC="${GRACE_SEC:-120}"
STATE_DIR="${STATE_DIR:-/var/lib/cmp-created-watchdog}"
ALERT_TO="${ALERT_TO:-dev@dtcdev.click}"
ALERT_FROM="${ALERT_FROM:-alerts@dtcdev.click}"
ALERT_FROM_NAME="${ALERT_FROM_NAME:-DTC Alerts}"
ALERT_MSMTP_ACCOUNT="${ALERT_MSMTP_ACCOUNT:-alerts}"
ALERT_REPEAT_MIN="${ALERT_REPEAT_MIN:-60}"
DRY_RUN="${DRY_RUN:-0}"

mkdir -p "$STATE_DIR"
NOW="$(date -u +%FT%TZ)"
NOW_EPOCH="$(date +%s)"

send_alert() { # subject, body, state_file
  local subject="$1" body="$2" state_file="$3"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "$NOW DRYRUN alert suppressed: $subject"
    return 0
  fi
  if [[ -f "$state_file" ]]; then
    local last
    last="$(cat "$state_file")"
    if (( NOW_EPOCH - last < ALERT_REPEAT_MIN * 60 )); then
      echo "$NOW DEDUPED alert: $subject"
      return 0
    fi
  fi

  local raw_from="$ALERT_FROM"
  local from_pat='<([^>]+)>'
  if [[ "$ALERT_FROM" =~ $from_pat ]]; then
    raw_from="${BASH_REMATCH[1]}"
  fi
  local from_header
  if [[ "$ALERT_FROM" == *"<"*">"* ]]; then
    from_header="$ALERT_FROM"
  elif [[ -n "${ALERT_FROM_NAME:-}" ]]; then
    from_header="${ALERT_FROM_NAME} <${raw_from}>"
  else
    from_header="$raw_from"
  fi

  local msmtp_bin sendmail_bin
  msmtp_bin="$(command -v msmtp 2>/dev/null || true)"
  sendmail_bin="$(command -v sendmail 2>/dev/null || true)"
  if [[ -z "$sendmail_bin" && -x /usr/sbin/sendmail ]]; then
    sendmail_bin="/usr/sbin/sendmail"
  fi

  local send_cmd=()
  if [[ -n "$msmtp_bin" && -x "$msmtp_bin" ]]; then
    send_cmd=("$msmtp_bin")
    if [[ -n "${ALERT_MSMTP_ACCOUNT:-}" ]]; then
      send_cmd+=(-a "$ALERT_MSMTP_ACCOUNT")
    fi
    send_cmd+=(-f "$raw_from" -t)
  elif [[ -n "$sendmail_bin" && -x "$sendmail_bin" ]]; then
    send_cmd=("$sendmail_bin")
    local target
    target="$(readlink -f "$sendmail_bin" 2>/dev/null || true)"
    if [[ "$target" == *"msmtp"* && -n "${ALERT_MSMTP_ACCOUNT:-}" ]]; then
      send_cmd+=(-a "$ALERT_MSMTP_ACCOUNT")
    fi
    send_cmd+=(-f "$raw_from" -t)
  fi

  if [[ ${#send_cmd[@]} -gt 0 ]] && printf 'From: %s\nSubject: %s\nTo: %s\n\n%s\n' "$from_header" "$subject" "$ALERT_TO" "$body" \
      | "${send_cmd[@]}" 2>/dev/null; then
    echo "$NOW ALERT sent: $subject -> $ALERT_TO"
  else
    echo "$NOW WARN: sendmail/msmtp failed, alert logged only: $subject"
  fi
  echo "$NOW_EPOCH" > "$state_file"
}

healed=0
checked=0
would=0

while IFS= read -r cid; do
  [[ -n "$cid" ]] || continue
  checked=$((checked + 1))
  name="$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null | sed 's#^/##')"
  image="$(docker inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null)"
  created="$(docker inspect --format '{{.Created}}' "$cid" 2>/dev/null)"
  # Skip Coolify helper one-shots — they are transient, never meant to be started manually.
  if [[ "$image" == *"coolify-helper"* ]]; then
    echo "$NOW SKIP helper one-shot: $name ($image)"
    continue
  fi
  created_epoch="$(date -d "$created" +%s 2>/dev/null || echo 0)"
  age=$((NOW_EPOCH - created_epoch))
  if (( age < GRACE_SEC )); then
    echo "$NOW SKIP fresh (${age}s < ${GRACE_SEC}s grace): $name ($cid)"
    continue
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "$NOW DRYRUN would start: $name ($cid) age=${age}s image=$image"
    would=$((would + 1))
    continue
  fi
  if docker start "$cid" >/dev/null 2>&1; then
    healed=$((healed + 1))
    echo "$NOW HEALED started stuck Created container: $name ($cid) age=${age}s image=$image"
    safe_name="$(echo "$name" | tr -c '[:alnum:]._-' '_')"
    send_alert \
      "[cmp-created-watchdog] STARTED stuck container $name" \
      "Container $name ($cid, image $image) sat in Created for ${age}s and was started at $NOW." \
      "$STATE_DIR/alert-$safe_name"
  else
    echo "$NOW ERROR failed to start: $name ($cid)"
  fi
done < <(docker ps -aq --filter status=created --filter label=coolify.managed=true 2>/dev/null)

if (( healed == 0 )); then
  if [[ "$DRY_RUN" == "1" && "$would" -gt 0 ]]; then
    echo "$NOW DRYRUN checked=$checked would-heal=$would"
  else
    echo "$NOW OK checked=$checked stuck=0"
  fi
fi
