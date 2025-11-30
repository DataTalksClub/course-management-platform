from django.conf import settings


def export_settings(request):
    dark_mode = False
    if request.user.is_authenticated:
        dark_mode = request.user.dark_mode
    return {
        "VERSION": settings.VERSION,
        "DARK_MODE": dark_mode,
    }
