import json
from urllib.parse import unquote

from django.shortcuts import redirect, render
from asgiref.sync import sync_to_async
from allauth.socialaccount.providers import registry
from allauth.socialaccount.models import SocialApp

from django.core.cache import cache

from django.conf import settings
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from loginas.utils import restore_original_login

from accounts.forms import AccountSettingsForm
from accounts.services.timezones import get_timezone_label, is_valid_timezone
from course_management.datamailer import (
    apply_email_preferences_to_user,
    update_email_preferences_for_user,
)
from courses.models import Enrollment

ACCOUNT_TOGGLE_FIELDS = {
    "dark_mode",
    "email_submission_confirmations",
    "email_deadline_reminders",
    "email_course_updates",
}


def disabled(request):
    return HttpResponse("This URL is disabled", status=403)


@login_required
def account_settings(request):
    user = request.user
    datamailer_preferences_loaded = apply_email_preferences_to_user(user)

    if request.method == "POST":
        data = request.POST.copy()
        if "preferred_timezone" not in data:
            data["preferred_timezone"] = user.preferred_timezone
        for field in ACCOUNT_TOGGLE_FIELDS:
            if getattr(user, field):
                data[field] = "on"
            else:
                data.pop(field, None)
        form = AccountSettingsForm(data, instance=user)
        if form.is_valid():
            form.save()
            return redirect("account_settings")
    else:
        form = AccountSettingsForm(instance=user)

    enrollments = (
        Enrollment.objects.filter(student=user)
        .select_related("course")
        .order_by("course__title")
    )

    browser_timezone = unquote(request.COOKIES.get("browser_timezone", ""))
    browser_timezone_label = ""
    if not user.preferred_timezone and is_valid_timezone(browser_timezone):
        browser_timezone_label = get_timezone_label(browser_timezone)

    return render(
        request,
        "accounts/account_settings.html",
        {
            "form": form,
            "enrollments": enrollments,
            "preferred_timezone_label": get_timezone_label(
                user.preferred_timezone
            ),
            "browser_timezone_label": browser_timezone_label,
            "datamailer_preferences_loaded": datamailer_preferences_loaded,
        },
    )


@login_required
@require_POST
def toggle_dark_mode(request):
    user = request.user
    user.dark_mode = not user.dark_mode
    user.save(update_fields=['dark_mode'])
    return JsonResponse({'dark_mode': user.dark_mode})


@login_required
@require_POST
def update_account_toggle(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")

    if field not in ACCOUNT_TOGGLE_FIELDS:
        return JsonResponse(
            {"error": "Unsupported account setting."},
            status=400,
        )

    enabled = value.lower() in {"1", "true", "yes", "on"}
    setattr(request.user, field, enabled)
    request.user.save(update_fields=[field])
    datamailer_synced = False
    if field.startswith("email_"):
        datamailer_synced = update_email_preferences_for_user(
            request.user,
            {field: enabled},
        )

    response = {
        "field": field,
        "value": enabled,
    }
    if field.startswith("email_"):
        response["datamailer_synced"] = datamailer_synced
    if field == "dark_mode":
        response["dark_mode"] = enabled
    return JsonResponse(response)


@login_required
@require_POST
def update_timezone_preference(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    timezone_name = data.get("timezone")
    if timezone_name is None:
        return JsonResponse({"error": "timezone field is required"}, status=400)
    if not isinstance(timezone_name, str):
        return JsonResponse({"error": "timezone must be a string"}, status=400)

    timezone_name = timezone_name.strip()
    if timezone_name and not is_valid_timezone(timezone_name):
        return JsonResponse({"error": "Invalid timezone"}, status=400)

    user = request.user
    if data.get("passive") and user.preferred_timezone:
        return JsonResponse(
            {
                "status": "ok",
                "timezone": user.preferred_timezone,
                "label": get_timezone_label(user.preferred_timezone),
            }
        )

    user.preferred_timezone = timezone_name
    user.save(update_fields=["preferred_timezone"])

    return JsonResponse(
        {
            "status": "ok",
            "timezone": user.preferred_timezone,
            "label": get_timezone_label(user.preferred_timezone),
        }
    )


@login_required
@csrf_exempt
@require_POST
def stop_impersonating(request):
    restore_original_login(request)
    return redirect("cadmin_course_list")


async def social_login_view(request):
    providers = await get_available_providers()

    return await sync_to_async(render)(
        request,
        "accounts/login.html",
        {"providers": providers},
    )


@sync_to_async
def get_available_providers():
    # Check if the data is in the cache
    cached_providers = cache.get('available_providers')
    if cached_providers is not None:
        return cached_providers

    providers = []

    site_id = settings.SITE_ID

    for provider, name in registry.as_choices():
        if not SocialApp.objects.filter(
            provider=provider, sites__id__exact=site_id
        ).exists():
            continue

        login_url = reverse(f"{provider}_login")
        providers.append({"name": name, "login_url": login_url})

    cache.set('available_providers', providers, 60 * 60)  # Cache for 60 minutes

    return providers
