#!/bin/sh
set -eu

case "${CMP_RUN_MIGRATIONS:-}" in
    1)
        echo "Applying database migrations under the CMP release lock"
        python manage.py migrate_with_lock
        ;;
    0)
        migration_wait_timeout="${CMP_MIGRATION_CHECK_TIMEOUT_SECONDS:-300}"
        case "$migration_wait_timeout" in
            ''|*[!0-9]*)
                echo "CMP_MIGRATION_CHECK_TIMEOUT_SECONDS must be a positive integer" >&2
                exit 1
                ;;
        esac
        if [ "$migration_wait_timeout" -lt 1 ]; then
            echo "CMP_MIGRATION_CHECK_TIMEOUT_SECONDS must be a positive integer" >&2
            exit 1
        fi

        elapsed=0
        until python manage.py migrate --check; do
            if [ "$elapsed" -ge "$migration_wait_timeout" ]; then
                echo "Timed out after ${migration_wait_timeout}s waiting for private web migrations" >&2
                exit 1
            fi
            echo "Migrations are pending; waiting for the private web owner (${elapsed}/${migration_wait_timeout}s)"
            sleep 5
            elapsed=$((elapsed + 5))
        done
        echo "Database migrations are up to date"
        ;;
    *)
        echo "CMP_RUN_MIGRATIONS must be set to 1 for the private web owner or 0 for a waiting service" >&2
        exit 1
        ;;
esac

# Embedded scoring worker fallback: prod Coolify compose (cmp-staging service)
# historically runs web-only, so a separate worker service may not exist.
# A normal image deploy is the only change guaranteed to reach prod, so the
# web entrypoint supervises run_scoring_worker when serving gunicorn traffic.
# Safe alongside a dedicated worker service (singleton worker_lock +
# idempotent scoring + stale reclaim): both may run without double-scoring.
# Disable explicitly with CMP_EMBEDDED_SCORING_WORKER=0 (staging/dev web set
# this because they run the dedicated worker service; prod leaves it unset
# and therefore defaults to enabled).
if [ "${CMP_EMBEDDED_SCORING_WORKER:-1}" != "0" ]; then
    case "$*" in
        *gunicorn*)
            echo "Starting embedded scoring worker (CMP_EMBEDDED_SCORING_WORKER=${CMP_EMBEDDED_SCORING_WORKER:-1})"
            ( while true; do python manage.py run_scoring_worker --interval 5; echo "embedded scoring worker exited, restarting in 5s"; sleep 5; done ) &
            ;;
    esac
fi

echo "Starting server"
exec "$@"
