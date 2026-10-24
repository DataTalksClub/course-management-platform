#!/usr/bin/env bash
# Unit tests for deploy/coolify/check-workers.sh and cmp-created-watchdog.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "  PASS: $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $label (expected '$expected', got '$actual')"
    FAIL=$((FAIL + 1))
  fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    echo "  PASS: $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $label (needle '$needle' not found in '$haystack')"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Test Suite: CMP Coolify Watchdogs ==="

TMP="$(mktemp -d /tmp/test-cmp-watchdogs.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# Create mock environment
mkdir -p "$TMP/bin" "$TMP/state"

# Mock logger
cat << 'EOF' > "$TMP/bin/logger"
#!/bin/bash
exit 0
EOF
chmod +x "$TMP/bin/logger"

# Mock msmtp
cat << EOF > "$TMP/bin/msmtp"
#!/bin/bash
echo "ARGS: \$*" >> "$TMP/msmtp.log"
cat >> "$TMP/msmtp.mail"
exit 0
EOF
chmod +x "$TMP/bin/msmtp"

# Mock sendmail as symlink to msmtp
ln -s "$TMP/bin/msmtp" "$TMP/bin/sendmail"

export PATH="$TMP/bin:$PATH"

# Test 1: check-workers.sh defaults (From header, envelope sender, msmtp account)
echo "[Test 1: check-workers.sh alert formatting with defaults]"
rm -f "$TMP/msmtp.log" "$TMP/msmtp.mail"

# Mock docker to simulate failed check (alarm)
cat << 'EOF' > "$TMP/bin/docker"
#!/bin/bash
if [[ "$1" == "ps" ]]; then
  echo "web-avcfd5kwb7cj9r1tx4ygjs6v-app-1"
  exit 0
fi
if [[ "$1" == "exec" ]]; then
  exit 1
fi
exit 0
EOF
chmod +x "$TMP/bin/docker"

CMP_MONITOR_STATE="$TMP/state/worker-1" \
CMP_ALERT_TO="dev@dtcdev.click" \
"$SCRIPT_DIR/check-workers.sh" || true

assert_eq "check-workers recorded status alarm" "alarm" "$(cat "$TMP/state/worker-1/status" 2>/dev/null || echo '')"
if [[ -f "$TMP/msmtp.log" ]]; then
  msmtp_args="$(cat "$TMP/msmtp.log")"
  assert_contains "msmtp account 'alerts' passed" "$msmtp_args" "-a alerts"
  assert_contains "msmtp envelope sender alerts@dtcdev.click" "$msmtp_args" "-f alerts@dtcdev.click"
else
  echo "  FAIL: msmtp was not invoked"
  FAIL=$((FAIL + 1))
fi

if [[ -f "$TMP/msmtp.mail" ]]; then
  mail_content="$(cat "$TMP/msmtp.mail")"
  assert_contains "From header contains DTC Alerts <alerts@dtcdev.click>" "$mail_content" "From: DTC Alerts <alerts@dtcdev.click>"
  assert_contains "To header contains dev@dtcdev.click" "$mail_content" "To: dev@dtcdev.click"
else
  echo "  FAIL: msmtp mail content empty"
  FAIL=$((FAIL + 1))
fi

# Test 2: check-workers.sh custom overrides
echo "[Test 2: check-workers.sh with custom overrides]"
rm -f "$TMP/msmtp.log" "$TMP/msmtp.mail"
CMP_MONITOR_STATE="$TMP/state/worker-2" \
CMP_ALERT_TO="ops@example.com" \
CMP_ALERT_FROM="Custom Alerts <custom@example.com>" \
CMP_ALERT_MSMTP_ACCOUNT="custom-acct" \
"$SCRIPT_DIR/check-workers.sh" || true

if [[ -f "$TMP/msmtp.log" ]]; then
  msmtp_args="$(cat "$TMP/msmtp.log")"
  assert_contains "msmtp account 'custom-acct' passed" "$msmtp_args" "-a custom-acct"
  assert_contains "msmtp envelope sender custom@example.com" "$msmtp_args" "-f custom@example.com"
fi
if [[ -f "$TMP/msmtp.mail" ]]; then
  mail_content="$(cat "$TMP/msmtp.mail")"
  assert_contains "From header matches custom override" "$mail_content" "From: Custom Alerts <custom@example.com>"
  assert_contains "To header matches custom override" "$mail_content" "To: ops@example.com"
fi

# Test 3: cmp-check-workers symlink works identically
echo "[Test 3: cmp-check-workers executable]"
rm -f "$TMP/msmtp.log" "$TMP/msmtp.mail"
CMP_MONITOR_STATE="$TMP/state/worker-3" \
CMP_ALERT_TO="dev@dtcdev.click" \
"$SCRIPT_DIR/cmp-check-workers" || true

assert_eq "cmp-check-workers recorded status alarm" "alarm" "$(cat "$TMP/state/worker-3/status" 2>/dev/null || echo '')"
if [[ -f "$TMP/msmtp.log" ]]; then
  msmtp_args="$(cat "$TMP/msmtp.log")"
  assert_contains "cmp-check-workers passed -a alerts" "$msmtp_args" "-a alerts"
fi

# Test 4: cmp-created-watchdog.sh alert formatting with defaults
echo "[Test 4: cmp-created-watchdog.sh alert formatting with defaults]"
rm -f "$TMP/msmtp.log" "$TMP/msmtp.mail"

# Mock docker to simulate stuck created container
cat << 'EOF' > "$TMP/bin/docker"
#!/bin/bash
if [[ "$1" == "ps" ]]; then
  echo "test-container-id-123"
  exit 0
fi
if [[ "$1" == "inspect" ]]; then
  if [[ "$*" == *"{{.Name}}"* ]]; then echo "/cmp-app-stuck"; exit 0; fi
  if [[ "$*" == *"{{.Config.Image}}"* ]]; then echo "cmp-web:latest"; exit 0; fi
  if [[ "$*" == *"{{.Created}}"* ]]; then echo "2026-01-01T00:00:00Z"; exit 0; fi
fi
if [[ "$1" == "start" ]]; then
  exit 0
fi
exit 0
EOF
chmod +x "$TMP/bin/docker"

STATE_DIR="$TMP/state/created-1" \
GRACE_SEC=0 \
ALERT_TO="dev@dtcdev.click" \
"$SCRIPT_DIR/cmp-created-watchdog.sh"

if [[ -f "$TMP/msmtp.log" ]]; then
  msmtp_args="$(cat "$TMP/msmtp.log")"
  assert_contains "created-watchdog passed -a alerts" "$msmtp_args" "-a alerts"
  assert_contains "created-watchdog envelope sender alerts@dtcdev.click" "$msmtp_args" "-f alerts@dtcdev.click"
else
  echo "  FAIL: msmtp was not invoked for created-watchdog"
  FAIL=$((FAIL + 1))
fi

if [[ -f "$TMP/msmtp.mail" ]]; then
  mail_content="$(cat "$TMP/msmtp.mail")"
  assert_contains "From header contains DTC Alerts <alerts@dtcdev.click>" "$mail_content" "From: DTC Alerts <alerts@dtcdev.click>"
  assert_contains "To header contains dev@dtcdev.click" "$mail_content" "To: dev@dtcdev.click"
  assert_contains "Subject contains STARTED stuck container" "$mail_content" "Subject: [cmp-created-watchdog] STARTED stuck container cmp-app-stuck"
else
  echo "  FAIL: msmtp mail content empty for created-watchdog"
  FAIL=$((FAIL + 1))
fi

# Test 5: cmp-created-watchdog.sh custom overrides
echo "[Test 5: cmp-created-watchdog.sh with custom overrides]"
rm -f "$TMP/msmtp.log" "$TMP/msmtp.mail"
STATE_DIR="$TMP/state/created-2" \
GRACE_SEC=0 \
ALERT_TO="custom-to@example.com" \
ALERT_FROM="Custom Created <custom-created@example.com>" \
ALERT_MSMTP_ACCOUNT="created-acct" \
"$SCRIPT_DIR/cmp-created-watchdog.sh"

if [[ -f "$TMP/msmtp.log" ]]; then
  msmtp_args="$(cat "$TMP/msmtp.log")"
  assert_contains "custom account 'created-acct' passed" "$msmtp_args" "-a created-acct"
  assert_contains "custom envelope sender custom-created@example.com" "$msmtp_args" "-f custom-created@example.com"
fi
if [[ -f "$TMP/msmtp.mail" ]]; then
  mail_content="$(cat "$TMP/msmtp.mail")"
  assert_contains "From header matches custom override" "$mail_content" "From: Custom Created <custom-created@example.com>"
fi

echo "=== Summary: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
