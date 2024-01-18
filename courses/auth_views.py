from django.shortcuts import render
from allauth.socialaccount.providers import registry
from allauth.socialaccount.models import SocialApp


def social_login_view(request):
    # Get available providers
    available_providers = []

    for provider in registry.get_class_list():
        # Check if provider is configured
        try:
            provider_app = SocialApp.objects.get(provider=provider.id)
            available_providers.append(provider)
        except SocialApp.DoesNotExist:
            # Skip providers that are not configured
            continue

    return render(request, 'social_login.html', {'providers': available_providers})
