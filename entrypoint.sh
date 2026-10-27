#!/bin/sh

echo "Apply database migrations"
python manage.py migrate

# Check if migrate command was successful
if [ $? -ne 0 ]; then
    echo "Failed to apply database migrations."
    exit 1
else
    echo "Database migrations applied successfully."
fi

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