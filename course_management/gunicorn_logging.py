"""Website-policy access logging, with CMP route parameters redacted."""
import re
import uuid

from gunicorn.glogging import Logger


def safe_path(path):
    # Health middleware handles /ping before Django's URL resolver.
    if path == '/ping':
        return path
    # Import at request time: the arbiter imports this before Django setup.
    from django.urls import Resolver404, resolve

    try:
        route = resolve(path).route
    except Resolver404:
        # An unknown URL can contain arbitrary email addresses or tokens.
        return '/[unmatched]'
    if '(?' in route or '^' in route or '$' in route:
        return '/[redacted]'
    return '/' + re.sub(r'<[^>]+>', '[redacted]', route).lstrip('/')


class PrivateAccessLogger(Logger):
    # AC4: the in-container 1/s readiness probe hits /api/health/ (~83k
    # lines/day, ~55% of log volume) at negligible CPU. Skip it in the
    # access log; cadence and alerting are unchanged.
    ACCESS_LOG_EXCLUDED_PATHS = frozenset({"/api/health/"})

    def access(self, resp, req, environ, request_time):
        if environ.get("PATH_INFO", "") in self.ACCESS_LOG_EXCLUDED_PATHS:
            return
        super().access(resp, req, environ, request_time)

    def atoms(self, resp, req, environ, request_time):
        values = super().atoms(resp, req, environ, request_time)
        values['U'] = safe_path(environ.get('PATH_INFO', ''))
        # Never trust caller-supplied IDs: they can contain PII or log injection.
        values['{x-request-id}o'] = uuid.uuid4().hex
        values['{x-correlation-id}o'] = '-'
        return values
