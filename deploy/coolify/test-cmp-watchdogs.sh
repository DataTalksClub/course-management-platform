#!/usr/bin/env bash
# Behavioral watchdog tests: real checks, hysteresis, recovery and Relay transport.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
export MAIL_LOG="$TMP/mail" BODY_LOG="$TMP/body" DOCKER_LOG="$TMP/docker" LOGGER_LOG="$TMP/logger"
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
 ps)
   if [[ "$*" == *'status=created'* ]]; then echo fake-created
   elif [[ "${CONTAINER_MODE:-single}" == none ]]; then :
   elif [[ "${CONTAINER_MODE:-single}" == mixed ]]; then
     printf '%s\n' web-avcfd5kwb7cj9r1tx4ygjs6v-bad web-avcfd5kwb7cj9r1tx4ygjs6v-good
   elif [[ "${CONTAINER_MODE:-single}" == forward ]]; then
     printf '%s\n' web-avcfd5kwb7cj9r1tx4ygjs6v-bad web-avcfd5kwb7cj9r1tx4ygjs6v-timeout
   elif [[ "${CONTAINER_MODE:-single}" == reversed ]]; then
     printf '%s\n' web-avcfd5kwb7cj9r1tx4ygjs6v-timeout web-avcfd5kwb7cj9r1tx4ygjs6v-bad
   else echo web-avcfd5kwb7cj9r1tx4ygjs6v-test; fi ;;
 exec)
   case "${CHECK_MODE:-alarm}:$2" in
     mixed-failures:*bad)
       printf '%s\n' '{"status":"warning","alarms":["outbox:failed"]}'
       exit 1 ;;
     mixed-failures:*timeout) exit 124 ;;
     mixed:web-avcfd5kwb7cj9r1tx4ygjs6v-bad)
       printf '%s\n' '{"status":"warning","alarms":["outbox:failed"]}'
       exit 1 ;;
     mixed:web-avcfd5kwb7cj9r1tx4ygjs6v-good|ok:*)
       printf '%s\n' '{"status":"ok","alarms":[]}'
       exit 0 ;;
     secret:*)
       printf '%s\n' '{"status":"ok","alarms":["SECRET_PERSONAL_DATA"]}'
       echo SECRET_STDERR_SENTINEL >&2
       exit 0 ;;
     timeout:*) exit 124 ;;
     all-codes:*)
       printf '%s\n' '{"status":"warning","alarms":["outbox:success_stale","outbox:failed","health:success_stale","health:failed","reminders:success_stale","reminders:failed","digest:success_stale","digest:failed","scoring:success_stale","scoring:failed","outbox:backlog_age","application_notifications:failed","application_notifications:backlog_age","scoring:backlog_age","scoring:stuck"]}'
       exit 1 ;;
     *)
       if [[ "${CHECK_FAIL:-1}" == 0 ]]; then
         printf '%s\n' '{"status":"ok","alarms":[]}'
         exit 0
       fi
       printf '%s\n' '{"status":"warning","alarms":["outbox:failed"]}'
       exit 1 ;;
   esac ;;
 inspect)
   case "$3" in
     '{{.Name}}') echo /fake-created ;;
     '{{.Config.Image}}') echo ghcr.io/example/cmp:test ;;
     '{{.Created}}') echo 2020-01-01T00:00:00Z ;;
   esac ;;
 start) exit 0 ;;
esac
STUB
printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$LOGGER_LOG"\n' > "$TMP/bin/logger"
chmod +x "$TMP/bin/"*
export CMP_MONITOR_STATE="$TMP/workers" CMP_ALERT_TO='ops@example.com,dev@dtcdev.click'
export DATAMAILER_API_KEY=must-not-override-monitor-client DATAMAILER_URL=https://must-not-override.invalid
# First failure is suppressed; second triggers exactly the configured recipients.
bash "$SCRIPT_DIR/check-workers.sh"
[[ ! -f "$MAIL_LOG" && "$(cat "$CMP_MONITOR_STATE/consecutive-failures")" == 1 ]]
grep -q 'categories=check_failed alarms=outbox:failed' "$LOGGER_LOG"
bash "$SCRIPT_DIR/check-workers.sh" && exit 1
[[ "$(wc -l < "$MAIL_LOG")" == 2 ]]
grep -q -- 'send --from alerts --to ops@example.com --subject CMP workers alarm' "$MAIL_LOG"
grep -q -- '--to dev@dtcdev.click' "$MAIL_LOG"
grep -q 'categories=check_failed; alarms=outbox:failed' "$BODY_LOG"
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
# A failed check is diagnosed with fixed categories and validated codes only.
rm -rf "$CMP_MONITOR_STATE"; rm -f "$MAIL_LOG" "$BODY_LOG" "$LOGGER_LOG"
CHECK_MODE=secret CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
grep -q 'categories=invalid_response alarms=none' "$LOGGER_LOG"
! grep -Eq 'SECRET_PERSONAL_DATA|SECRET_STDERR_SENTINEL' "$LOGGER_LOG" "$BODY_LOG" "$MAIL_LOG"
echo 'PASS: malformed output is redacted from logs and alerts'
# Every code emitted by check_cmp_workers is accepted and retained for diagnosis.
rm -rf "$CMP_MONITOR_STATE"; rm -f "$MAIL_LOG" "$BODY_LOG" "$LOGGER_LOG"
CHECK_MODE=all-codes CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
expected_alarms='application_notifications:backlog_age,application_notifications:failed,digest:failed,digest:success_stale,health:failed,health:success_stale,outbox:backlog_age,outbox:failed,outbox:success_stale,reminders:failed,reminders:success_stale,scoring:backlog_age,scoring:failed,scoring:stuck,scoring:success_stale'
grep -Fq "categories=check_failed; alarms=$expected_alarms" "$BODY_LOG"
echo 'PASS: all emitted alarm codes pass validation and appear in diagnostics'
# During a rolling replacement, one valid container remains sufficient.
rm -rf "$CMP_MONITOR_STATE"; rm -f "$MAIL_LOG" "$LOGGER_LOG"
CONTAINER_MODE=mixed CHECK_MODE=mixed bash "$SCRIPT_DIR/check-workers.sh"
[[ "$(cat "$CMP_MONITOR_STATE/status")" == ok && "$(cat "$CMP_MONITOR_STATE/consecutive-failures")" == 0 ]]
[[ ! -f "$MAIL_LOG" ]]
echo 'PASS: mixed rolling containers preserve any-success semantics'
# Fixed categories cover an empty container set and timeout failures.
rm -rf "$CMP_MONITOR_STATE"; rm -f "$LOGGER_LOG"
CONTAINER_MODE=none CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
grep -q 'categories=no_container alarms=none' "$LOGGER_LOG"
rm -rf "$CMP_MONITOR_STATE"; rm -f "$LOGGER_LOG"
CHECK_MODE=timeout CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
grep -q 'categories=timeout alarms=none' "$LOGGER_LOG"
echo 'PASS: no-container and timeout failures use fixed categories'
# Failed-container category diagnostics are order independent.
rm -f "$MAIL_LOG" "$BODY_LOG" "$LOGGER_LOG"
CONTAINER_MODE=forward CHECK_MODE=mixed-failures CMP_MONITOR_STATE="$TMP/forward" \
  CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
cp "$BODY_LOG" "$TMP/forward-body"
rm -f "$MAIL_LOG" "$BODY_LOG" "$LOGGER_LOG"
CONTAINER_MODE=reversed CHECK_MODE=mixed-failures CMP_MONITOR_STATE="$TMP/reversed" \
  CMP_FAIL_THRESHOLD=1 bash "$SCRIPT_DIR/check-workers.sh" && exit 1
grep -Fq 'categories=check_failed,timeout; alarms=outbox:failed' "$BODY_LOG"
cmp "$TMP/forward-body" "$BODY_LOG"
echo 'PASS: mixed failure diagnostics are stable across container order'
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
