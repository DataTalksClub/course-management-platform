from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.social_login_view, name='login'),
    path('signup/', views.social_login_view, name='accounts_signup'),
    path('email/', views.disabled),
    path('password/reset/', views.disabled),
]