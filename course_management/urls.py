from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', include('loginas.urls')),
    path('admin/', admin.site.urls),

    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),

    path("", include("courses.urls")),
]
