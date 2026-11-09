"""Marketing attribution: UTM parameters and external referrer.

A landing visit with ``utm_*`` query parameters (or an external
``Referer``) is remembered in the session per campaign and stamped on the
registration when the application saves. The latest tagged visit wins;
untagged visits never erase earlier attribution.
"""

from urllib.parse import urlsplit

UTM_FIELDS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
)
FIELD_MAX_LENGTH = {
    "utm_source": 100,
    "utm_medium": 100,
    "utm_campaign": 150,
    "utm_content": 150,
    "utm_term": 150,
    "landing_referrer": 500,
}
SESSION_KEY = "utm_attribution"


def _clean(field, value):
    return (value or "").strip()[: FIELD_MAX_LENGTH[field]]


def _external_referrer(request):
    referrer = request.META.get("HTTP_REFERER", "")
    host = urlsplit(referrer).hostname
    if not host or host == request.get_host().split(":")[0]:
        return ""
    return referrer


def remember_attribution(request, campaign) -> None:
    values = {
        field: _clean(field, request.GET.get(field))
        for field in UTM_FIELDS
    }
    values = {field: value for field, value in values.items() if value}
    if values:
        values["landing_referrer"] = _clean(
            "landing_referrer", _external_referrer(request)
        )
    else:
        referrer = _clean("landing_referrer", _external_referrer(request))
        stored = request.session.get(SESSION_KEY, {})
        if not referrer or str(campaign.pk) in stored:
            return
        values["landing_referrer"] = referrer
    stored = request.session.get(SESSION_KEY, {})
    stored[str(campaign.pk)] = values
    request.session[SESSION_KEY] = stored


def attribute_registration(request, registration) -> None:
    stored = request.session.get(SESSION_KEY, {})
    values = stored.pop(str(registration.campaign_id), None)
    request.session[SESSION_KEY] = stored
    if not values:
        return
    for field, value in values.items():
        setattr(registration, field, value)
    registration.save(update_fields=[*values, "updated_at"])
