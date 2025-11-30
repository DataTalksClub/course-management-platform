from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.social_login_view, name='login'),
    path('email/', views.disabled),
    path('password/reset/', views.disabled),
    path('toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
]