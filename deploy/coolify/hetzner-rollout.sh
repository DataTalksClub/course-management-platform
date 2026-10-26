#!/usr/bin/env bash
# Hetzner-side poller for the private production CMP release service.
# Its Compose web has traefik.enable=false. The shared rolling-web follower
# promotes this healthy source to the native public Application; see README.md.
#
# Why: GitHub Actions runners cannot reliably reach Coolify
# http://169.58.119.163:8000 (timeout), so the GHA deploy job may pin the
# compose but fail to trigger the rollout. This poller runs on RMTHZ
# (Hetzner, which reaches :8000) every 5 min via cron and converges:
#   newest GHCR tag (YYYYMMDD-HHMMSS-<7>) == Coolify running image.
#
# No secrets in this file. Runtime inputs (env, with safe defaults):
#   GHCR_PAT_FILE    read:packages PAT (default ~/tmp/secrets/coolify-ghcr-read.pat)
#   COOLIFY_TOKEN_FILE Coolify API token (default ~/tmp/secrets/coolify-api-169.58.119.163.token)
#   COOLIFY_URL      (default http://169.58.119.163:8000)
#   SERVICE_UUID     (default avcfd5kwb7cj9r1tx4ygjs6v = cmp-staging)
#   STATE_DIR        (default ~/.local/state/cmp-coolify-rollout)
#
# Cron (RMTHZ):
#   */5 * * * * flock -n ~/.local/state/cmp-coolify-rollout.lock /home/alexey/git/course-management-platform/deploy/coolify/hetzner-rollout.sh >> ~/.local/state/cmp-coolify-rollout/cron.log 2>&1
set -euo pipefail

GHCR_PAT_FILE="${GHCR_PAT_FILE:-$HOME/tmp/secrets/coolify-ghcr-read.pat}"
COOLIFY_TOKEN_FILE="${COOLIFY_TOKEN_FILE:-$HOME/tmp/secrets/coolify-api-169.58.119.163.token}"
COOLIFY_URL="${COOLIFY_URL:-http://169.58.119.163:8000}"
SERVICE_UUID="${SERVICE_UUID:-avcfd5kwb7cj9r1tx4ygjs6v}"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/cmp-coolify-rollout}"
IMAGE_REF="ghcr.io/datatalksclub/course-management-platform"

mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/rollout.log"
echo "=== $(date -u +%FT%TZ) rollout check ===" | tee -a "$LOG"

export GHCR_PAT_FILE COOLIFY_TOKEN_FILE COOLIFY_URL SERVICE_UUID IMAGE_REF STATE_DIR LOG

python3 - <<'PY' 2>&1 | tee -a "$LOG"
import base64, json, os, re, subprocess, sys, urllib.request

ghcr_pat = open(os.environ["GHCR_PAT_FILE"]).read().strip()
coolify_token = open(os.environ["COOLIFY_TOKEN_FILE"]).read().strip()
base = os.environ["COOLIFY_URL"].rstrip("/")
uuid = os.environ["SERVICE_UUID"]
image_ref = os.environ["IMAGE_REF"]
state_dir = os.environ["STATE_DIR"]
TAG_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{7}$")

def gh_versions():
    req = urllib.request.Request(
        "https://api.github.com/orgs/DataTalksClub/packages/container/course-management-platform/versions?per_page=10",
        headers={"Authorization": f"Bearer {ghcr_pat}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def coolify(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {coolify_token}", "Accept": "application/json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        return resp.status, (json.loads(body) if body else {})

# 1. newest GHCR tag in ECR format (versions API is most-recent-first)
latest = None
for v in gh_versions():
    tags = (v.get("metadata", {}).get("container", {}).get("tags", []) or [])
    good = sorted(t for t in tags if TAG_RE.match(t or ""))
    if good:
        latest = good[-1]
        break
if not latest:
    print("no ECR-format GHCR tag found; nothing to do")
    sys.exit(0)
print(f"latest GHCR tag: {latest}")

# 2. running image + pinned VERSION in Coolify (both must match latest:
# /api/health/ reports VERSION, and the public rolling follower mirrors it)
_st, svc = coolify("GET", f"/api/v1/services/{uuid}")
running = (svc["applications"][0]["image"] or "")
print(f"coolify running image: {running}")
raw = svc["docker_compose_raw"]
_version_match = re.search(r"(?m)^\s*VERSION\s*:\s*(.+?)\s*$", raw)
compose_version = (_version_match.group(1).strip().strip("'\"") if _version_match else None)
print(f"coolify compose VERSION: {compose_version}")
if running == f"{image_ref}:{latest}" and compose_version == latest:
    print("converged: nothing to do")
    sys.exit(0)

# 3. pin compose image + VERSION env, then force deploy (same as GHA deploy job)
new, n = re.subn(re.escape(f"{image_ref}:") + r"[^\s'\"]+", f"{image_ref}:{latest}", raw, count=1)
if n != 1:
    raise SystemExit(f"could not pin image in compose (matches={n})")
new, m = re.subn(
    r"(?m)^(\s*VERSION\s*:\s*)([^\s'\"]+|'[^']*'|\"[^\"]*\")\s*$",
    r"\g<1>" + latest,
    new,
    count=1,
)
if m != 1:
    raise SystemExit(f"could not pin VERSION in compose (matches={m})")
coolify("PATCH", f"/api/v1/services/{uuid}",
        {"docker_compose_raw": base64.b64encode(new.encode()).decode()})
print(f"pinned compose image and VERSION to {latest}")
_st, out = coolify("POST", f"/api/v1/deploy?uuid={uuid}&force=true")
print(json.dumps(out)[:200])
with open(os.path.join(state_dir, "last_rollout"), "w") as f:
    f.write(f"{latest}\n")
print(f"private release triggered for {latest}; verify source health, then native public promotion")
PY
