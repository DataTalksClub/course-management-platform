from django.shortcuts import render
from asgiref.sync import sync_to_async
from allauth.socialaccount.providers import registry
from allauth.socialaccount.models import SocialApp

from django.conf import settings
from django.urls import reverse


async def social_login_view(request):
    # Get available providers
    available_providers = await get_available_providers(request)

    return render(
        request,
        "social_login.html",
        {"providers": available_providers},
    )


@sync_to_async
def get_available_providers(request):
    providers = []

    site_id = settings.SITE_ID

    for provider, name in registry.as_choices():
        if not SocialApp.objects.filter(
            provider=provider, sites__id__exact=site_id
        ).exists():
            continue

        login_url = reverse(f"{provider}_login")
        providers.append({"name": name, "login_url": login_url})

    return providers
