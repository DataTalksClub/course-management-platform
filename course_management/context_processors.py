from django.conf import settings


def export_settings(request):
    return {
        "VERSION": settings.VERSION
    }
