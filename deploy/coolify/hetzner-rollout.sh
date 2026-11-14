#!/usr/bin/env bash
# Hetzner-side poller for the private production CMP release service.
# Its Compose web has traefik.enable=false. The shared rolling-web follower
# promotes this healthy source to the native public Application; see README.md.
#
# This script is installed as a versioned copy by machine-management and runs
# on a five-minute systemd timer. It reaches Coolify through the supervised
# SSH tunnel at 127.0.0.1:18000, so API tokens never cross the network in HTTP.
# GitHub Actions may be unable to reach Coolify; the poller then converges:
#   newest GHCR tag (YYYYMMDD-HHMMSS-<7>) == Coolify running image.
#
# No secrets in this file. Runtime inputs (env, with safe defaults):
#   GHCR_PAT_FILE    read:packages PAT (default ~/tmp/secrets/coolify-ghcr-read.pat)
#   COOLIFY_TOKEN_FILE Coolify API token (default ~/tmp/secrets/coolify-api-169.58.119.163.token)
#   COOLIFY_URL      HTTPS endpoint or supervised SSH tunnel
#                    (default http://127.0.0.1:18000)
#   SERVICE_UUID     (default avcfd5kwb7cj9r1tx4ygjs6v = cmp-staging)
#   STATE_DIR        (default ~/.local/state/cmp-coolify-rollout)
#   HOLD_FILE        touch to pause convergence (default $STATE_DIR/hold)
#   GITHUB_API_URL   GitHub REST base (default https://api.github.com)
#
# A GitHub API rate limit (403/429 with x-ratelimit-remaining: 0 or
# retry-after) is shared with every other client of the same account. It is
# transient: the check is skipped with exit 0 and retried on the next timer
# run, changing nothing. Any other GitHub error still fails the unit.
set -euo pipefail

GHCR_PAT_FILE="${GHCR_PAT_FILE:-$HOME/tmp/secrets/coolify-ghcr-read.pat}"
COOLIFY_TOKEN_FILE="${COOLIFY_TOKEN_FILE:-$HOME/tmp/secrets/coolify-api-169.58.119.163.token}"
COOLIFY_URL="${COOLIFY_URL:-http://127.0.0.1:18000}"
COOLIFY_URL="${COOLIFY_URL%/}"
SERVICE_UUID="${SERVICE_UUID:-avcfd5kwb7cj9r1tx4ygjs6v}"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/cmp-coolify-rollout}"
HOLD_FILE="${HOLD_FILE:-$STATE_DIR/hold}"
IMAGE_REF="ghcr.io/datatalksclub/course-management-platform"
GITHUB_API_URL="${GITHUB_API_URL:-https://api.github.com}"
GITHUB_API_URL="${GITHUB_API_URL%/}"

case "$COOLIFY_URL" in
  https://?*|http://127.0.0.1:18000) ;;
  *)
    echo "COOLIFY_URL must use HTTPS or the supervised SSH tunnel (http://127.0.0.1:18000)" >&2
    exit 2
    ;;
esac

mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/rollout.log"
echo "=== $(date -u +%FT%TZ) rollout check ===" | tee -a "$LOG"

if [[ -f "$HOLD_FILE" ]]; then
  echo "hold file active; automatic release convergence paused" | tee -a "$LOG"
  exit 0
fi

export GHCR_PAT_FILE COOLIFY_TOKEN_FILE COOLIFY_URL SERVICE_UUID IMAGE_REF STATE_DIR LOG GITHUB_API_URL

python3 - <<'PY' 2>&1 | tee -a "$LOG"
import base64, json, os, re, subprocess, sys, time, urllib.error, urllib.request

ghcr_pat = open(os.environ["GHCR_PAT_FILE"]).read().strip()
coolify_token = open(os.environ["COOLIFY_TOKEN_FILE"]).read().strip()
base = os.environ["COOLIFY_URL"].rstrip("/")
uuid = os.environ["SERVICE_UUID"]
image_ref = os.environ["IMAGE_REF"]
state_dir = os.environ["STATE_DIR"]
TAG_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{7}$")

def gh_versions():
    req = urllib.request.Request(
        os.environ["GITHUB_API_URL"].rstrip("/")
        + "/orgs/DataTalksClub/packages/container/course-management-platform/versions?per_page=10",
        headers={"Authorization": f"Bearer {ghcr_pat}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as error:
        headers = error.headers or {}
        limited = error.code in (403, 429) and (
            headers.get("x-ratelimit-remaining") == "0" or headers.get("retry-after")
        )
        if not limited:
            raise
        reset = headers.get("x-ratelimit-reset") or ""
        when = (time.strftime("%H:%M:%SZ", time.gmtime(int(reset)))
                if reset.isdigit() else "unknown")
        # Shared account quota; nothing was read or written. Retry next run.
        print(f"GitHub API rate limited (HTTP {error.code}; reset {when}); "
              "skipping this check, no changes made")
        sys.exit(0)

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

# 1. newest timestamped GHCR release tag (versions API is most-recent-first)
latest = None
for v in gh_versions():
    tags = (v.get("metadata", {}).get("container", {}).get("tags", []) or [])
    good = sorted(t for t in tags if TAG_RE.match(t or ""))
    if good:
        latest = good[-1]
        break
if not latest:
    print("no timestamped GHCR release tag found; nothing to do")
    sys.exit(0)
print(f"latest GHCR tag: {latest}")

# 2. running image + pinned VERSIONs in Coolify (all must match latest:
# /api/health/ reports VERSION, and the public rolling follower mirrors it;
# the service also runs a worker with the same image/VERSION)
_st, svc = coolify("GET", f"/api/v1/services/{uuid}")
apps = svc.get("applications") or [{}]
web_apps = [a for a in apps if a.get("name") == "web"] or apps[:1]
running = (web_apps[0].get("image") or "")
print(f"coolify running image: {running}")
raw = svc["docker_compose_raw"]
compose_versions = [
    match.group(1).strip().strip("'\"")
    for match in re.finditer(r"(?m)^\s*VERSION\s*:\s*(.+?)\s*$", raw)
]
print(f"coolify compose VERSIONs: {compose_versions}")
if (
    running == f"{image_ref}:{latest}"
    and compose_versions
    and all(v == latest for v in compose_versions)
):
    print("converged: nothing to do")
    sys.exit(0)

# 3. pin compose images + VERSION envs, then force deploy (same as GHA
# deploy job; pins web + worker services, all VERSION occurrences)
new, n = re.subn(re.escape(f"{image_ref}:") + r"[^\s'\"]+", f"{image_ref}:{latest}", raw)
if n < 1:
    raise SystemExit(f"could not pin image in compose (matches={n})")
new, m = re.subn(
    r"(?m)^(\s*VERSION\s*:\s*)([^\s'\"]+|'[^']*'|\"[^\"]*\")\s*$",
    r"\g<1>" + latest,
    new,
)
if m < 1:
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
