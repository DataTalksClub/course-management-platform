from django.urls import path

from . import views

urlpatterns = [
    # Courses
    path(
        "courses/",
        views.courses_list_view,
        name="api_courses_list",
    ),
    path(
        "courses/<slug:course_slug>/",
        views.course_detail_view,
        name="api_course_detail",
    ),

    # Homeworks
    path(
        "courses/<slug:course_slug>/homeworks/",
        views.homeworks_view,
        name="api_homeworks",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/",
        views.homework_detail_view,
        name="api_homework_detail",
    ),

    # Projects
    path(
        "courses/<slug:course_slug>/projects/",
        views.projects_view,
        name="api_projects",
    ),
    path(
        "courses/<slug:course_slug>/projects/<int:project_id>/",
        views.project_detail_view,
        name="api_project_detail",
    ),

    # Questions
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/questions/",
        views.questions_view,
        name="api_questions",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/questions/<int:question_id>/",
        views.question_detail_view,
        name="api_question_detail",
    ),
]
