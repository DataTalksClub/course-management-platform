"""Loaded by Gunicorn from /code for Docker and Coolify commands."""
# Keep the rolling health probe responsive while requests occupy workers.
# Separate processes also let CPU-heavy Django views use more than one core;
# threads leave capacity for liveness during database/network waits.
workers = 4
threads = 2
accesslog = '-'
# Canonical website format: no query, client IP, referrer or user agent.
access_log_format = (
    '%(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(D)s '
    'request_id="%({x-request-id}o)s" correlation_id="%({x-correlation-id}o)s"'
)
logger_class = 'course_management.gunicorn_logging.PrivateAccessLogger'
