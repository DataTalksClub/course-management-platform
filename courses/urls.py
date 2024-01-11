from django.urls import path
from . import views


urlpatterns = [
    path("", views.course_list, name="course_list"),
    path(
        "<slug:course_slug>/",
        views.course_view,
        name="course",
    ),
    path(
        "<slug:course_slug>/leaderboard",
        views.leaderboard_view,
        name="leaderboard",
    ),
    path(
        "<slug:course_slug>/leaderboard/<int:enrollment_id>/",
        views.leaderboard_score_breakdown_view,
        name="leaderboard_score_breakdown",
    ),
    path(
        "<slug:course_slug>/enrollment",
        views.enrollment_view,
        name="enrollment",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>",
        views.project_view,
        name="project",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>",
        views.homework_view,
        name="homework",
    ),

]
