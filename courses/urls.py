from django.urls import path

from .views import course
from .views import homework
from .views import project


urlpatterns = [
    path("", course.course_list, name="course_list"),
    path(
        "<slug:course_slug>/",
        course.course_view,
        name="course",
    ),
    path(
        "<slug:course_slug>/leaderboard",
        course.leaderboard_view,
        name="leaderboard",
    ),
    path(
        "<slug:course_slug>/leaderboard/<int:enrollment_id>/",
        course.leaderboard_score_breakdown_view,
        name="leaderboard_score_breakdown",
    ),
    path(
        "<slug:course_slug>/enrollment",
        course.enrollment_view,
        name="enrollment",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>",
        project.project_view,
        name="project",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval",
        project.projects_eval_view,
        name="projects_eval",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval/<int:review_id>",
        project.projects_eval_submit,
        name="projects_eval_submit",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>",
        homework.homework_view,
        name="homework",
    ),
]
