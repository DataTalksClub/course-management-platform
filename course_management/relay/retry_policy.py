"""Shared retry policy for Relay transactional sends.

4xx means "don't bother retrying" — except 429 (rate limited) and
CloudFront/WAF rate-limit blocks, which arrive as 403 with a CloudFront
error page instead of a Relay JSON error. Those must back off briefly
and retry, not park for 24 hours.
"""

import requests


def _response_body(exc) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        return response.text or ""
    except Exception:
        return ""


def _response_headers(exc) -> dict[str, str]:
    response = getattr(exc, "response", None)
    raw_headers = getattr(response, "headers", None) or {}
    return {
        str(k).lower(): str(v).lower()
        for k, v in raw_headers.items()
    }


def is_waf_rate_block(exc) -> bool:
    """True when a 403 looks like a CloudFront/WAF rate-limit block."""
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", 0) != 403:
        return False
    headers = _response_headers(exc)
    if "application/json" in headers.get("content-type", ""):
        return False
    if "cloudfront" in headers.get("server", ""):
        return True
    body = _response_body(exc).lower()
    if "cloudfront" in body and (
        "request blocked" in body or "could not be satisfied" in body
    ):
        return True
    return "the request could not be satisfied" in body and "<html" in body


def is_rate_limit_error(exc) -> bool:
    """True when Relay or CloudFront WAF rejected the request due to rate limit."""
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", 0) == 429:
        return True
    return is_waf_rate_block(exc)


def is_retryable_relay_http_error(exc) -> bool:
    """True for transient Relay/edge HTTP errors (CloudFront 403, 429, 5xx)."""
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", 0) or 0
    if not status_code:
        return False
    return not is_permanent_relay_error(exc)


def retry_after_seconds(exc) -> float | None:
    """Parse numeric Retry-After header in seconds, if present."""
    headers = _response_headers(exc)
    raw = headers.get("retry-after", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return max(0.0, value)


def is_permanent_relay_error(exc) -> bool:
    """True for Relay 4xx that will never succeed on retry.

    429 and WAF rate-limit blocks are transient: same payload will go
    through once the limit window passes.
    """
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", 0) or 0
    if not status_code:
        return False
    if status_code == 429:
        return False
    if is_waf_rate_block(exc):
        return False
    return 400 <= status_code < 500
