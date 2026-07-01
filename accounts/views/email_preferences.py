from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from course_management.datamailer.preferences import (
    get_email_preferences_for_user,
    update_email_preferences_for_user,
)


EMAIL_PREFERENCE_FIELDS = {
    "email_submission_confirmations",
    "email_deadline_reminders",
    "email_course_updates",
}


@dataclass(frozen=True)
class EmailPreferenceUpdate:
    field: str
    enabled: bool


@login_required
@require_http_methods(["GET", "POST"])
def account_email_preferences(request):
    if request.method == "GET":
        return _account_email_preferences_get_response(request.user)

    return _account_email_preferences_update_response(request)


def _email_preferences_unavailable_response():
    response = JsonResponse(
        {"error": "Email preferences are unavailable."},
        status=503,
    )
    return response


def _account_email_preferences_get_response(user):
    preferences = get_email_preferences_for_user(user)
    if preferences is None:
        return _email_preferences_unavailable_response()
    payload = {"preferences": preferences}
    response = JsonResponse(payload)
    return response


def _email_preference_update_payload(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    if field not in EMAIL_PREFERENCE_FIELDS:
        response = JsonResponse(
            {"error": "Unsupported email preference."},
            status=400,
        )
        return None, response

    enabled = value.lower() in {"1", "true", "yes", "on"}
    update = EmailPreferenceUpdate(field, enabled)
    return update, None


def _account_email_preferences_update_response(request):
    update, error_response = _email_preference_update_payload(request)
    if error_response:
        return error_response

    preferences = {update.field: update.enabled}
    datamailer_synced = update_email_preferences_for_user(
        request.user,
        preferences,
    )
    if not datamailer_synced:
        return _email_preferences_unavailable_response()

    return _email_preference_update_success_response(update)


def _email_preference_update_success_response(update):
    response = JsonResponse(
        {
            "field": update.field,
            "value": update.enabled,
            "datamailer_synced": True,
        }
    )
    return response
