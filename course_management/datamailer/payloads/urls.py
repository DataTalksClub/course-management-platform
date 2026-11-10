from django.urls import reverse

from ..client import public_url


def public_route_url(route_name, route_kwargs=None):
    if route_kwargs is None:
        path = reverse(route_name)
    else:
        path = reverse(route_name, kwargs=route_kwargs)
    url = public_url(path)
    return url


UNSUBSCRIBE_TOKEN_PLACEHOLDER = "{token}"


def unsubscribe_url_template():
    """CMP's unsubscribe URL with Relay's per-recipient ``{token}`` placeholder.

    Campaign payloads carry this so Relay links and List-Unsubscribe headers
    point at CMP, not Relay's own /unsubscribe page.
    """
    url = public_route_url("account_unsubscribe", {"token": "RELAYTOKEN"})
    return url.replace("RELAYTOKEN", UNSUBSCRIBE_TOKEN_PLACEHOLDER)
