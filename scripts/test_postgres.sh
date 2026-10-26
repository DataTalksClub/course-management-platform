#!/usr/bin/env bash
# A disposable local database; never uses application credentials or data.
set -euo pipefail
cd "$(dirname "$0")/.."
container=$(docker run --detach --rm \
    -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=cmp_test \
    -p 127.0.0.1::5432 postgres:16)
trap 'docker stop "$container" >/dev/null' EXIT
ready=false
for attempt in {1..30}; do
    if docker exec "$container" pg_isready -U postgres -d cmp_test >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
done
if [[ "$ready" != true ]]; then
    echo 'PostgreSQL did not become ready' >&2
    exit 1
fi
port=$(docker port "$container" 5432/tcp | cut -d: -f2)
export DATABASE_URL="postgresql://postgres@127.0.0.1:${port}/cmp_test"
uv sync --locked
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pytest "$@"
