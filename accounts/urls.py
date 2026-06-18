from django.urls import path
from . import views

urlpatterns = [
    path('settings/', views.account_settings, name='account_settings'),
    path('login/', views.social_login_view, name='login'),
    path('email/', views.disabled),
    path('password/reset/', views.disabled),
    path('toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    path(
        'settings/toggle/',
        views.update_account_toggle,
        name='update_account_toggle',
    ),
    path('stop-impersonating/', views.stop_impersonating, name='stop_impersonating'),
]
