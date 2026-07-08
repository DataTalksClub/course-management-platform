from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from course_management.observability import record_event


LOCAL_ACCOUNT_TOGGLE_FIELDS = {
    "dark_mode",
}


@login_required
@require_POST
def toggle_dark_mode(request):
    user = request.user
    user.dark_mode = not user.dark_mode
    user.save(update_fields=["dark_mode"])
    record_event(
        "account.toggle_updated",
        request=request,
        properties={
            "field": "dark_mode",
            "enabled": user.dark_mode,
        },
    )
    payload = {"dark_mode": user.dark_mode}
    response = JsonResponse(payload)
    return response


@login_required
@require_POST
def update_account_toggle(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")

    if field not in LOCAL_ACCOUNT_TOGGLE_FIELDS:
        response = JsonResponse(
            {"error": "Unsupported account setting."},
            status=400,
        )
        return response

    enabled = value.lower() in {"1", "true", "yes", "on"}
    setattr(request.user, field, enabled)
    request.user.save(update_fields=[field])
    record_event(
        "account.toggle_updated",
        request=request,
        properties={
            "field": field,
            "enabled": enabled,
        },
    )

    payload = {
        "field": field,
        "value": enabled,
    }
    if field == "dark_mode":
        payload["dark_mode"] = enabled
    response = JsonResponse(payload)
    return response
