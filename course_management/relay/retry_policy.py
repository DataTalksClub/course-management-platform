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


def is_waf_rate_block(exc) -> bool:
    """True when a 403 looks like a CloudFront/WAF rate-limit block."""
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", 0) != 403:
        return False
    body = _response_body(exc).lower()
    return "cloudfront" in body and (
        "request blocked" in body or "could not be satisfied" in body
    )


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
