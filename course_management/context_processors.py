from django.conf import settings
from loginas.utils import is_impersonated_session


def export_settings(request):
    dark_mode = False
    if request.user.is_authenticated:
        dark_mode = request.user.dark_mode
    return {
        "VERSION": settings.VERSION,
        "DARK_MODE": dark_mode,
        "SHOW_WRAPPED": settings.SHOW_WRAPPED,
        "IS_IMPERSONATING": is_impersonated_session(request),
    }
