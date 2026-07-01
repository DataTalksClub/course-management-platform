from django.contrib import admin
from django.urls import include, path

loginas_urls = include("loginas.urls")
accounts_urls = include("accounts.urls")
allauth_urls = include("allauth.urls")
api_urls = include("api.urls")
cadmin_urls = include("cadmin.urls")
courses_urls = include("courses.urls")

urlpatterns = [
    path("admin/", loginas_urls),
    path("admin/", admin.site.urls),

    path("accounts/", accounts_urls),
    path("accounts/", allauth_urls),

    path("api/", api_urls),
    path("cadmin/", cadmin_urls),
    path("", courses_urls),
]
