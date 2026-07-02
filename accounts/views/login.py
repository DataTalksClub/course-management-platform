from asgiref.sync import sync_to_async
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers import registry
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse


async def social_login_view(request):
    providers = await get_available_providers()
    context = {"providers": providers}
    render_async = sync_to_async(render)

    response = await render_async(
        request,
        "accounts/login.html",
        context,
    )
    return response


@sync_to_async
def get_available_providers():
    cached_providers = cache.get("available_providers")
    if cached_providers is not None:
        return cached_providers

    providers = []
    site_id = settings.SITE_ID
    provider_choices = registry.as_choices()
    for provider, name in provider_choices:
        provider_enabled = SocialApp.objects.filter(
            provider=provider,
            sites__id__exact=site_id,
        ).exists()
        if not provider_enabled:
            continue

        login_url = reverse(f"{provider}_login")
        provider_record = {"name": name, "login_url": login_url}
        providers.append(provider_record)

    cache.set("available_providers", providers, 60 * 60)
    return providers
