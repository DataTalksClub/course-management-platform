import logging
import re
from urllib.parse import quote

import requests
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from course_management.datamailer.client import validate_relay_config
from course_management.observability import record_event

logger = logging.getLogger(__name__)

# Relay issues url-safe per-recipient tokens; reject anything else before it
# is placed in the Relay URL path.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
RELAY_UNSUBSCRIBE_TIMEOUT_SECONDS = 15
ONE_CLICK_FIELD = "List-Unsubscribe"
ONE_CLICK_VALUE = "One-Click"


def _unsubscribe_page(request, status, **context):
    return render(request, "accounts/unsubscribe.html", context, status=status)


def _failure(request, one_click, reason, status=503):
    """Fail loudly: error log plus an event, and never claim success."""
    logger.error("cmp_unsubscribe_failed reason=%s", reason)
    record_event(
        "account.unsubscribe_failed",
        request=request,
        properties={"reason": reason, "one_click": one_click},
    )
    if one_click:
        return HttpResponse(status=status, headers={"Retry-After": "60"})
    return _unsubscribe_page(request, status, unavailable=True)


def _forward_to_relay(token):
    """Apply the unsubscribe on Relay's one-click endpoint; return the HTTP response."""
    is_valid, reason, config = validate_relay_config()
    if not is_valid:
        raise RuntimeError(f"relay config unavailable: {reason}")
    url = f"{config.url.rstrip('/')}/unsubscribe/{quote(token, safe='')}"
    return requests.post(
        url,
        data={ONE_CLICK_FIELD: ONE_CLICK_VALUE},
        timeout=RELAY_UNSUBSCRIBE_TIMEOUT_SECONDS,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    """CMP-owned unsubscribe endpoint for emails sent through Relay campaigns.

    GET shows a confirmation page (link prefetchers must not unsubscribe
    anyone). POST, from the page or an RFC 8058 one-click mail client,
    applies the unsubscribe on Relay (suppression) using the per-recipient
    token Relay put in the link. Relay then posts ``subscription.unsubscribed``
    to /api/datamailer/events, which updates the CMP preference.
    """
    if not TOKEN_PATTERN.match(token):
        record_event("account.unsubscribe_invalid_token", request=request)
        return _unsubscribe_page(request, 404, invalid=True)

    if request.method == "GET":
        return _unsubscribe_page(request, 200)

    one_click = request.POST.get(ONE_CLICK_FIELD) == ONE_CLICK_VALUE
    try:
        response = _forward_to_relay(token)
    except (requests.RequestException, RuntimeError):
        logger.exception("cmp_unsubscribe_relay_request_failed")
        return _failure(request, one_click, "relay_unreachable")

    if response.status_code == 404:
        record_event("account.unsubscribe_invalid_token", request=request)
        if one_click:
            return HttpResponse(status=404)
        return _unsubscribe_page(request, 404, invalid=True)
    if not response.ok:
        return _failure(
            request, one_click, f"relay_status_{response.status_code}"
        )

    record_event(
        "account.unsubscribe_applied",
        request=request,
        properties={"one_click": one_click},
    )
    if one_click:
        return HttpResponse(status=204)
    return _unsubscribe_page(request, 200, confirmed=True)
