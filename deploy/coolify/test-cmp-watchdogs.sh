#!/usr/bin/env bash
# Behavioral watchdog tests: real checks, hysteresis, recovery and Relay transport.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${WATCHDOG_TEST_TMPDIR:-${TMPDIR:-/tmp}}/cmp-watchdogs.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
export LOGGER_LOG="$TMP/logger"
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
 ps) [[ "${DISCOVERY_FAIL:-0}" == 0 ]] || exit 1
     [[ "${NO_CONTAINERS:-0}" == 0 ]] || exit 0
     if [[ "$*" == *'status=created'* ]]; then echo fake-created; else echo web-avcfd5kwb7cj9r1tx4ygjs6v-test
       [[ "${SECOND_RUNNER_OK:-0}" != 1 ]] || echo web-avcfd5kwb7cj9r1tx4ygjs6v-healthy
     fi ;;
 exec) [[ "${SECOND_RUNNER_OK:-0}" != 1 || "$2" != *-healthy ]] || exit 0
       printf '%s\n' "${CHECK_OUTPUT:-}"; exit "${CHECK_FAIL:-1}" ;;
 inspect)
   case "$3" in
     '{{.Name}}') echo /fake-created ;;
     '{{.Config.Image}}') echo ghcr.io/example/cmp:test ;;
     '{{.Created}}') echo 2020-01-01T00:00:00Z ;;
   esac ;;
 start) exit 0 ;;
esac
STUB
cat > "$TMP/bin/logger" <<'STUB'
#!/bin/bash
printf '%s\n' "$*" >> "$LOGGER_LOG"
STUB
chmod +x "$TMP/bin/"*
export CMP_MONITOR_STATE="$TMP/workers" CMP_ALERT_TO='ops@example.com,dev@dtcdev.click'
export DATAMAILER_API_KEY=must-not-override-monitor-client DATAMAILER_URL=https://must-not-override.invalid
# Retain only allowlisted labels; arbitrary command output must never reach mail/logs.
export CHECK_OUTPUT='{"status":"warning","alarms":["scoring:success_stale","outbox:backlog_age","secret-canary",{"recipient":"recipient-canary@example.invalid"}]}
Traceback: secret-canary recipient-canary@example.invalid'
# First failure is suppressed; second triggers exactly the configured recipients.
bash "$SCRIPT_DIR/check-workers.sh"
[[ ! -f "$MAIL_LOG" && "$(cat "$CMP_MONITOR_STATE/consecutive-failures")" == 1 ]]
bash "$SCRIPT_DIR/check-workers.sh" && exit 1
[[ "$(wc -l < "$MAIL_LOG")" == 2 ]]
grep -q -- 'send --from alerts --to ops@example.com --subject CMP workers alarm' "$MAIL_LOG"
grep -q -- '--to dev@dtcdev.click' "$MAIL_LOG"
grep -q 'scoring:success_stale' "$BODY_LOG"
grep -q 'outbox:backlog_age' "$LOGGER_LOG"
grep -q 'check_exit=1' "$LOGGER_LOG"
! grep -Eq 'secret-canary|recipient-canary' "$BODY_LOG" "$LOGGER_LOG"
[[ -f "$CMP_MONITOR_STATE/last-check" ]]
cp "$MAIL_LOG" "$TMP/before"
bash "$SCRIPT_DIR/check-workers.sh" && exit 1
cmp "$TMP/before" "$MAIL_LOG"
CHECK_FAIL=0 bash "$SCRIPT_DIR/check-workers.sh"
[[ "$(wc -l < "$MAIL_LOG")" == 4 && "$(cat "$CMP_MONITOR_STATE/status")" == ok ]]
grep -q -- '--subject CMP workers ok' "$MAIL_LOG"
echo 'PASS: hysteresis, dedupe, recovery, recipients and safe alarm evidence'
# Empty output, timeout, missing runner and discovery errors are distinct from job alarms.
for scenario in empty timeout missing discovery; do
  export CMP_MONITOR_STATE="$TMP/$scenario"
  case "$scenario" in
    empty) CHECK_OUTPUT='' CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
           grep -q 'check_exit=1 alarms=unavailable' "$CMP_MONITOR_STATE/last-check" ;;
    timeout) CHECK_FAIL=124 CHECK_OUTPUT='' CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
             grep -q 'check_exit=124 alarms=unavailable' "$CMP_MONITOR_STATE/last-check" ;;
    missing) NO_CONTAINERS=1 CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
             grep -q 'no_runner' "$CMP_MONITOR_STATE/last-check" ;;
    discovery) DISCOVERY_FAIL=1 CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
               grep -q 'container_discovery_failed' "$CMP_MONITOR_STATE/last-check" ;;
  esac
  CHECK_FAIL=0 CHECK_OUTPUT='{"status":"ok","alarms":[]}' bash "$SCRIPT_DIR/check-workers.sh"
  [[ "$(cat "$CMP_MONITOR_STATE/status")" == ok ]]
done
# One healthy overlapping runner is sufficient, even if its sibling failed.
CMP_MONITOR_STATE="$TMP/overlap" SECOND_RUNNER_OK=1 bash "$SCRIPT_DIR/check-workers.sh"
[[ "$(cat "$TMP/overlap/status")" == ok ]]
echo 'PASS: execution failures, missing runners and rolling overlap have separate evidence'
export CMP_MONITOR_STATE="$TMP/workers"
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
