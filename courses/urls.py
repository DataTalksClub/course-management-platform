from django.urls import path
from . import views


urlpatterns = [
    path("", views.course_list, name="course_list"),
    path("<slug:course_slug>/", views.course_detail, name="course_detail"),
    path(
        "<slug:course_slug>/<slug:homework_slug>/",
        views.homework_detail,
        name="homework_detail",
    ),
    path(
        "<slug:course_slug>/<slug:homework_slug>/submit",
        views.submit_homework,
        name="submit_homework",
    ),
]
