from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import AccountSettingsForm
from accounts.services.timezones import browser_timezone_name, get_timezone_label
from accounts.views.account_toggles import LOCAL_ACCOUNT_TOGGLE_FIELDS
from course_management.datamailer.preference_categories import (
    EMAIL_PREFERENCE_CATEGORIES,
)
from courses.models import Enrollment


@login_required
def account_settings(request):
    user = request.user
    form = _account_settings_form(request, user)

    if request.method == "POST" and form.is_valid():
        form.save()
        response = redirect("account_settings")
        return response

    context = _account_settings_context(request, user, form)
    response = render(
        request,
        "accounts/account_settings.html",
        context,
    )
    return response


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

    browser_timezone = browser_timezone_name(request)
    if not browser_timezone:
        return ""
    return get_timezone_label(browser_timezone)
