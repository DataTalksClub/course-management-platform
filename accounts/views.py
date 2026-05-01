from django.shortcuts import redirect, render
from asgiref.sync import sync_to_async
from allauth.socialaccount.providers import registry
from allauth.socialaccount.models import SocialApp

from django.core.cache import cache

from django.conf import settings
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from accounts.forms import AccountSettingsForm
from courses.models import Enrollment


def disabled(request):
    return HttpResponse("This URL is disabled", status=403)


@login_required
def account_settings(request):
    user = request.user

    if request.method == "POST":
        form = AccountSettingsForm(request.POST, instance=user)
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

    return render(
        request,
        "accounts/account_settings.html",
        {
            "form": form,
            "enrollments": enrollments,
        },
    )


@login_required
@require_POST
def toggle_dark_mode(request):
    user = request.user
    user.dark_mode = not user.dark_mode
    user.save(update_fields=['dark_mode'])
    return JsonResponse({'dark_mode': user.dark_mode})


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
