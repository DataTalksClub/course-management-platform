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
    def atoms(self, resp, req, environ, request_time):
        values = super().atoms(resp, req, environ, request_time)
        values['U'] = safe_path(environ.get('PATH_INFO', ''))
        # Never trust caller-supplied IDs: they can contain PII or log injection.
        values['{x-request-id}o'] = uuid.uuid4().hex
        values['{x-correlation-id}o'] = '-'
        return values
