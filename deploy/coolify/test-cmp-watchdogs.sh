#!/usr/bin/env bash
# Behavioral watchdog tests: real checks, hysteresis, recovery and Relay transport.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
export MAIL_LOG="$TMP/mail" BODY_LOG="$TMP/body" DOCKER_LOG="$TMP/docker"
export PATH="$TMP/bin:$PATH" DATAMAILER_BIN="$TMP/bin/datamailer"
cat > "$TMP/bin/datamailer" <<'STUB'
#!/bin/bash
[[ -z "${DATAMAILER_API_KEY:-}" && -z "${DATAMAILER_URL:-}" ]]
printf '%s\n' "$*" >> "$MAIL_LOG"
cat >> "$BODY_LOG"
exit "${MAIL_FAIL:-0}"
STUB
cat > "$TMP/bin/docker" <<'STUB'
#!/bin/bash
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$1" in
 ps) if [[ "$*" == *'status=created'* ]]; then echo fake-created; else echo web-avcfd5kwb7cj9r1tx4ygjs6v-test; fi ;;
 exec) exit "${CHECK_FAIL:-1}" ;;
 inspect)
   case "$3" in
     '{{.Name}}') echo /fake-created ;;
     '{{.Config.Image}}') echo ghcr.io/example/cmp:test ;;
     '{{.Created}}') echo 2020-01-01T00:00:00Z ;;
   esac ;;
 start) exit 0 ;;
esac
STUB
printf '#!/bin/bash\nexit 0\n' > "$TMP/bin/logger"
chmod +x "$TMP/bin/"*
export CMP_MONITOR_STATE="$TMP/workers" CMP_ALERT_TO='ops@example.com,dev@dtcdev.click'
export DATAMAILER_API_KEY=must-not-override-monitor-client DATAMAILER_URL=https://must-not-override.invalid
# First failure is suppressed; second triggers exactly the configured recipients.
bash "$SCRIPT_DIR/check-workers.sh"
[[ ! -f "$MAIL_LOG" && "$(cat "$CMP_MONITOR_STATE/consecutive-failures")" == 1 ]]
bash "$SCRIPT_DIR/check-workers.sh" && exit 1
[[ "$(wc -l < "$MAIL_LOG")" == 2 ]]
grep -q -- 'send --from alerts --to ops@example.com --subject CMP workers alarm' "$MAIL_LOG"
grep -q -- '--to dev@dtcdev.click' "$MAIL_LOG"
cp "$MAIL_LOG" "$TMP/before"
bash "$SCRIPT_DIR/check-workers.sh" && exit 1
cmp "$TMP/before" "$MAIL_LOG"
CHECK_FAIL=0 bash "$SCRIPT_DIR/check-workers.sh"
[[ "$(wc -l < "$MAIL_LOG")" == 4 && "$(cat "$CMP_MONITOR_STATE/status")" == ok ]]
grep -q -- '--subject CMP workers ok' "$MAIL_LOG"
echo 'PASS: hysteresis, dedupe, recovery, recipients and fixed Relay sender'
# A failed send must not suppress the next alert attempt.
rm -rf "$CMP_MONITOR_STATE"; rm "$MAIL_LOG"
MAIL_FAIL=1 CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
[[ ! -f "$CMP_MONITOR_STATE/last-alert" ]]
echo 'PASS: failed Relay requests do not advance alert timestamp'
# Created-container heal sends through Relay and keeps dedupe/dry-run behavior.
export STATE_DIR="$TMP/created" ALERT_TO=custom@example.com
rm "$MAIL_LOG"
bash "$SCRIPT_DIR/cmp-created-watchdog.sh"
grep -q -- 'send --from alerts --to custom@example.com --subject \[cmp-created-watchdog\]' "$MAIL_LOG"
cp "$MAIL_LOG" "$TMP/before"
bash "$SCRIPT_DIR/cmp-created-watchdog.sh"
cmp "$TMP/before" "$MAIL_LOG"
DRY_RUN=1 STATE_DIR="$TMP/dry" bash "$SCRIPT_DIR/cmp-created-watchdog.sh"
cmp "$TMP/before" "$MAIL_LOG"
echo 'PASS: Created healing retains dedupe and dry-run isolation'
# Both source proof modes send only to dev and do not run Docker or write state.
for script in check-workers.sh cmp-created-watchdog.sh; do
 rm -f "$MAIL_LOG" "$DOCKER_LOG"
 CMP_MONITOR_STATE="$TMP/no-state" STATE_DIR="$TMP/no-state" bash "$SCRIPT_DIR/$script" --test-alert
 [[ ! -e "$TMP/no-state" && ! -e "$DOCKER_LOG" ]]
 [[ "$(wc -l < "$MAIL_LOG")" == 1 ]]
 grep -q -- 'send --from alerts --to dev@dtcdev.click --subject TEST' "$MAIL_LOG"
done
echo 'PASS: source-specific dev-only proof modes'
