from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.social_login_view, name='login'),
    path('login/email/', views.email_login_view, name='email_login'),
    path('login/email/send-code/', views.send_verification_code, name='send_verification_code'),
    path('login/email/verify-code/', views.verify_code, name='verify_code'),
    path('email/', views.disabled),
    path('password/reset/', views.disabled),
]