"""Loaded by Gunicorn from /code for Docker and Coolify commands."""
accesslog = '-'
# Canonical website format: no query, client IP, referrer or user agent.
access_log_format = (
    '%(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(D)s '
    'request_id="%({x-request-id}o)s" correlation_id="%({x-correlation-id}o)s"'
)
logger_class = 'course_management.gunicorn_logging.PrivateAccessLogger'
