import threading
import time

from django.conf import settings
from django.http import HttpResponse

from course_management.observability import report_exception


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass ALLOWED_HOSTS check for health check endpoint
        if request.path.startswith("/ping") and request.method == "GET":
            return HttpResponse("OK")
        return self.get_response(request)


# Per-IP token bucket state for RateLimitMiddleware. Module-level so the
# bucket survives across requests within one worker process. Each Gunicorn
# worker tracks its own buckets; with N workers the effective global limit
# is approximately N times the configured average. The configured values
# assume the production worker count.
_rate_limit_buckets: dict = {}
_rate_limit_lock = threading.Lock()


def reset_rate_limit_state():
    """Clear all per-IP buckets. Used by tests to isolate cases."""
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


def rate_limit_exempt_path(path):
    exempt_exact = set(
        getattr(
            settings,
            "RATELIMIT_EXEMPT_PATHS",
            ["/", "/api/health/", "/ping", "/robots.txt"],
        )
    )
    if path in exempt_exact:
        return True
    exempt_prefixes = tuple(
        getattr(settings, "RATELIMIT_EXEMPT_PREFIXES", ["/static/"])
    )
    return path.startswith(exempt_prefixes)


def rate_limit_client_ip(request):
    # Traefik appends the peer address to X-Forwarded-For, so the last
    # entry is the real client (a spoofed first entry is ignored).
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        entries = [part.strip() for part in forwarded_for.split(",")]
        entries = [entry for entry in entries if entry]
        if entries:
            return entries[-1]
    return request.META.get("REMOTE_ADDR", "")


class RateLimitMiddleware:
    """Per-IP token-bucket rate limiter (Traefik-style: average + burst).

    Allows ``RATELIMIT_AVERAGE`` requests per second on average with short
    bursts up to ``RATELIMIT_BURST``. Health and monitor paths
    (``RATELIMIT_EXEMPT_PATHS`` / ``RATELIMIT_EXEMPT_PREFIXES``) are never
    limited. Exceeding clients receive HTTP 429.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "RATELIMIT_ENABLED", True):
            return self.get_response(request)
        if rate_limit_exempt_path(request.path):
            return self.get_response(request)

        average = float(getattr(settings, "RATELIMIT_AVERAGE", 10))
        burst = int(getattr(settings, "RATELIMIT_BURST", 30))
        now = time.monotonic()
        client_ip = rate_limit_client_ip(request) or "unknown"

        with _rate_limit_lock:
            tokens, last_seen = _rate_limit_buckets.get(
                client_ip, (float(burst), now)
            )
            tokens = min(float(burst), tokens + (now - last_seen) * average)
            if tokens < 1.0:
                _rate_limit_buckets[client_ip] = (tokens, now)
                allowed = False
            else:
                _rate_limit_buckets[client_ip] = (tokens - 1.0, now)
                allowed = True

        if not allowed:
            response = HttpResponse(
                "Rate limit exceeded. Slow down and try again.",
                status=429,
                content_type="text/plain",
            )
            response["Retry-After"] = "1"
            return response
        return self.get_response(request)


class ObservabilityExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        report_exception(
            exception,
            request=request,
            properties={"source": "django.request"},
        )
        return None
