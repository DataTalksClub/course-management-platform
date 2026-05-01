from django.urls import path

from . import views as data_views


urlpatterns = [
    # Health check (public, no auth required)
    path(
        "health/",
        data_views.health_view,
        name="api_health",
    ),

    # Course criteria (public, no auth required)
    path(
        "courses/<slug:course_slug>/course-criteria.yaml",
        data_views.course_criteria_yaml_view,
        name="api_course_criteria_yaml",
    ),

    # Leaderboard data (public, no auth required)
    path(
        "courses/<slug:course_slug>/leaderboard.yaml",
        data_views.leaderboard_data_view,
        name="api_course_leaderboard",
    ),

    # Data API endpoints (require auth)
    path(
        "courses/<slug:course_slug>/homeworks/<slug:homework_slug>/submissions",
        data_views.homework_data_view,
        name="api_homework_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/projects/<slug:project_slug>/submissions",
        data_views.project_data_view,
        name="api_project_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/graduates",
        data_views.graduates_data_view,
        name="api_course_graduates",
    ),
    path(
        "courses/<slug:course_slug>/certificates",
        data_views.bulk_update_enrollment_certificates_view,
        name="api_course_certificates",
    ),
]
