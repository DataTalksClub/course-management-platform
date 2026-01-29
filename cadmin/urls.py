from django.urls import path

from . import views

urlpatterns = [
    path("", views.course_list, name="cadmin_course_list"),
    path("<slug:course_slug>/", views.course_admin, name="cadmin_course"),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/score",
        views.homework_score,
        name="cadmin_homework_score",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/set-correct-answers",
        views.homework_set_correct_answers,
        name="cadmin_homework_set_correct_answers",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/submissions",
        views.homework_submissions,
        name="cadmin_homework_submissions",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/assign-reviews",
        views.project_assign_reviews,
        name="cadmin_project_assign_reviews",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/score",
        views.project_score,
        name="cadmin_project_score",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/submissions",
        views.project_submissions,
        name="cadmin_project_submissions",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/submissions/<int:submission_id>/edit",
        views.project_submission_edit,
        name="cadmin_project_submission_edit",
    ),
    path(
        "<slug:course_slug>/enrollment/<int:enrollment_id>/edit",
        views.enrollment_edit,
        name="cadmin_enrollment_edit",
    ),
]
