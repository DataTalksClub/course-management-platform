from django.urls import path

from accounts.views.account_settings import account_settings
from accounts.views.account_toggles import (
    toggle_dark_mode,
    update_account_toggle,
)
from accounts.views.disabled import disabled
from accounts.views.email_preferences import account_email_preferences
from accounts.views.impersonation import stop_impersonating
from accounts.views.login import social_login_view
from accounts.views.timezone import update_timezone_preference

urlpatterns = [
    path('settings/', account_settings, name='account_settings'),
    path('login/', social_login_view, name='login'),
    path('email/', disabled),
    path('password/reset/', disabled),
    path('toggle-dark-mode/', toggle_dark_mode, name='toggle_dark_mode'),
    path(
        'settings/toggle/',
        update_account_toggle,
        name='update_account_toggle',
    ),
    path(
        'settings/email-preferences/',
        account_email_preferences,
        name='account_email_preferences',
    ),
    path(
        'settings/timezone/',
        update_timezone_preference,
        name='update_timezone_preference',
    ),
    path('stop-impersonating/', stop_impersonating, name='stop_impersonating'),
]
