from django.urls import path

from .views import course
from .views import homework
from .views import project
from .views import data


urlpatterns = [
    path("", course.course_list, name="course_list"),
    path(
        "<slug:course_slug>/",
        course.course_view,
        name="course",
    ),
    path(
        "<slug:course_slug>/projects",
        course.list_all_project_submissions_view,
        name="list_all_project_submissions",
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
        "<slug:course_slug>/dashboard",
        course.dashboard_view,
        name="dashboard",
    ),

    # project
    path(
        "<slug:course_slug>/project/<slug:project_slug>",
        project.project_view,
        name="project",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/list",
        project.projects_list_view,
        name="project_list",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval",
        project.projects_eval_view,
        name="projects_eval",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/results",
        project.project_results,
        name="project_results",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/stats",
        project.project_statistics,
        name="project_statistics",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval/<int:review_id>",
        project.projects_eval_submit,
        name="projects_eval_submit",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval/add/<int:submission_id>",
        project.projects_eval_add,
        name="projects_eval_add",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/eval/delete/<int:review_id>",
        project.projects_eval_delete,
        name="projects_eval_delete",
    ),

    # homework
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>",
        homework.homework_view,
        name="homework",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/stats",
        homework.homework_statistics,
        name="homework_statistics",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/submissions",
        homework.homework_submissions,
        name="homework_submissions",
    ),

    # API
    path(
        "data/<slug:course_slug>/homework/<slug:homework_slug>",
        data.homework_data_view,
        name="data_homework",
    ),
    path(
        "data/<slug:course_slug>/project/<slug:project_slug>",
        data.project_data_view,
        name="data_project",
    ),
    path(
        "data/<slug:course_slug>/graduates",
        data.graduates_data_view,
        name="data_graduates",
    ),
    path(
        "data/<slug:course_slug>/update-certificate",
        data.update_enrollment_certificate_view,
        name="data_update_certificate",
    ),
    path(
        "<slug:course_slug>/course-criteria.yaml",
        data.course_criteria_yaml_view,
        name="course_criteria_yaml",
    ),
]
