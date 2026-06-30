import json
from dataclasses import dataclass
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
from django.views.decorators.http import require_POST, require_http_methods
from loginas.utils import restore_original_login

from accounts.forms import AccountSettingsForm
from accounts.services.timezones import get_timezone_label, is_valid_timezone
from course_management.datamailer.preferences import (
    EMAIL_PREFERENCE_CATEGORIES,
    get_email_preferences_for_user,
    update_email_preferences_for_user,
)
from courses.models import Enrollment

LOCAL_ACCOUNT_TOGGLE_FIELDS = {
    "dark_mode",
}

EMAIL_PREFERENCE_FIELDS = {
    "email_submission_confirmations",
    "email_deadline_reminders",
    "email_course_updates",
}


@dataclass(frozen=True)
class EmailPreferenceUpdate:
    field: str
    enabled: bool


def disabled(request):
    return HttpResponse("This URL is disabled", status=403)


@login_required
def account_settings(request):
    user = request.user
    form = _account_settings_form(request, user)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("account_settings")

    context = _account_settings_context(request, user, form)
    return render(
        request,
        "accounts/account_settings.html",
        context,
    )


def _account_settings_form(request, user):
    if request.method != "POST":
        return AccountSettingsForm(instance=user)

    post_data = _account_settings_post_data(request, user)
    return AccountSettingsForm(
        post_data,
        instance=user,
    )


def _account_settings_post_data(request, user):
    data = request.POST.copy()
    if "preferred_timezone" not in data:
        data["preferred_timezone"] = user.preferred_timezone
    _preserve_local_account_toggles(data, user)
    return data


def _preserve_local_account_toggles(data, user):
    for field in LOCAL_ACCOUNT_TOGGLE_FIELDS:
        if getattr(user, field):
            data[field] = "on"
        else:
            data.pop(field, None)


def _account_settings_context(request, user, form):
    enrollments = _account_settings_enrollments(user)
    preferred_timezone_label = get_timezone_label(user.preferred_timezone)
    browser_timezone_label = _browser_timezone_label(request, user)

    return {
        "form": form,
        "enrollments": enrollments,
        "preferred_timezone_label": preferred_timezone_label,
        "browser_timezone_label": browser_timezone_label,
        "email_preference_categories": EMAIL_PREFERENCE_CATEGORIES,
    }


def _account_settings_enrollments(user):
    enrollments = (
        Enrollment.objects.filter(student=user)
        .select_related("course")
        .order_by("course__title")
    )
    return enrollments


def _browser_timezone_label(request, user):
    if user.preferred_timezone:
        return ""

    browser_timezone_cookie = request.COOKIES.get("browser_timezone", "")
    browser_timezone = unquote(browser_timezone_cookie)
    if not is_valid_timezone(browser_timezone):
        return ""
    return get_timezone_label(browser_timezone)


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

    if field not in LOCAL_ACCOUNT_TOGGLE_FIELDS:
        return JsonResponse(
            {"error": "Unsupported account setting."},
            status=400,
        )

    enabled = value.lower() in {"1", "true", "yes", "on"}
    setattr(request.user, field, enabled)
    request.user.save(update_fields=[field])

    response = {
        "field": field,
        "value": enabled,
    }
    if field == "dark_mode":
        response["dark_mode"] = enabled
    return JsonResponse(response)


@login_required
@require_http_methods(["GET", "POST"])
def account_email_preferences(request):
    if request.method == "GET":
        return _account_email_preferences_get_response(request.user)

    return _account_email_preferences_update_response(request)


def _email_preferences_unavailable_response():
    return JsonResponse(
        {"error": "Email preferences are unavailable."},
        status=503,
    )


def _account_email_preferences_get_response(user):
    preferences = get_email_preferences_for_user(user)
    if preferences is None:
        return _email_preferences_unavailable_response()
    return JsonResponse({"preferences": preferences})


def _email_preference_update_payload(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    if field not in EMAIL_PREFERENCE_FIELDS:
        response = JsonResponse(
            {"error": "Unsupported email preference."},
            status=400,
        )
        return None, response

    enabled = _enabled_from_request_value(value)
    update = EmailPreferenceUpdate(field, enabled)
    return update, None


def _enabled_from_request_value(value):
    return value.lower() in {"1", "true", "yes", "on"}


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
    return JsonResponse(
        {
            "field": update.field,
            "value": update.enabled,
            "datamailer_synced": True,
        }
    )


def _parse_timezone_request(request):
    try:
        data = json.loads(request.body)
        return data, None
    except (json.JSONDecodeError, ValueError):
        return None, "Invalid JSON"


def _validated_timezone_name(data):
    timezone_name = data.get("timezone")
    if timezone_name is None:
        return None, "timezone field is required"
    if not isinstance(timezone_name, str):
        return None, "timezone must be a string"

    timezone_name = timezone_name.strip()
    if timezone_name and not is_valid_timezone(timezone_name):
        return None, "Invalid timezone"

    return timezone_name, None


def _timezone_preference_response(timezone_name):
    timezone_label = get_timezone_label(timezone_name)
    return JsonResponse(
        {
            "status": "ok",
            "timezone": timezone_name,
            "label": timezone_label,
        }
    )


def _should_keep_saved_timezone(data, user):
    return data.get("passive") and user.preferred_timezone


def _save_timezone_preference(user, timezone_name):
    user.preferred_timezone = timezone_name
    user.save(update_fields=["preferred_timezone"])


@login_required
@require_POST
def update_timezone_preference(request):
    data, error = _parse_timezone_request(request)
    if error:
        return JsonResponse({"error": error}, status=400)

    timezone_name, error = _validated_timezone_name(data)
    if error:
        return JsonResponse({"error": error}, status=400)

    user = request.user
    if _should_keep_saved_timezone(data, user):
        return _timezone_preference_response(user.preferred_timezone)

    _save_timezone_preference(user, timezone_name)
    return _timezone_preference_response(user.preferred_timezone)


@login_required
@csrf_exempt
@require_POST
def stop_impersonating(request):
    restore_original_login(request)
    return redirect("cadmin_course_list")


async def social_login_view(request):
    providers = await get_available_providers()
    context = {"providers": providers}
    render_async = sync_to_async(render)

    return await render_async(
        request,
        "accounts/login.html",
        context,
    )


@sync_to_async
def get_available_providers():
    # Check if the data is in the cache
    cached_providers = cache.get('available_providers')
    if cached_providers is not None:
        return cached_providers

    providers = []

    site_id = settings.SITE_ID

    provider_choices = registry.as_choices()
    for provider, name in provider_choices:
        if not SocialApp.objects.filter(
            provider=provider, sites__id__exact=site_id
        ).exists():
            continue

        login_url = reverse(f"{provider}_login")
        provider_record = {"name": name, "login_url": login_url}
        providers.append(provider_record)

    cache.set('available_providers', providers, 60 * 60)  # Cache for 60 minutes

    return providers
