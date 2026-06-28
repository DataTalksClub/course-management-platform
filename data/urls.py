"""
Compatibility URL module for legacy imports.

The live `/api/` routes are registered from `api.urls`. Keep this module only
while external code may still import `data.urls` directly.
"""

from django.urls import path

from api import views as api_views


urlpatterns = [
    # Health check (public, no auth required)
    path(
        "health/",
        api_views.health_view,
        name="api_health",
    ),
    # Course criteria (public, no auth required)
    path(
        "courses/<slug:course_slug>/course-criteria.yaml",
        api_views.course_criteria_yaml_view,
        name="api_course_criteria_yaml",
    ),
    # Leaderboard data (public, no auth required)
    path(
        "courses/<slug:course_slug>/leaderboard.yaml",
        api_views.leaderboard_data_view,
        name="api_course_leaderboard",
    ),
    # Data API endpoints (require auth)
    path(
        "courses/<slug:course_slug>/homeworks/<slug:homework_slug>/submissions",
        api_views.homework_data_view,
        name="api_homework_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/projects/<slug:project_slug>/submissions",
        api_views.project_data_view,
        name="api_project_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/graduates",
        api_views.graduates_data_view,
        name="api_course_graduates",
    ),
    path(
        "courses/<slug:course_slug>/certificates",
        api_views.bulk_update_enrollment_certificates_view,
        name="api_course_certificates",
    ),
    path(
        "datamailer/events",
        api_views.datamailer_event_webhook,
        name="api_datamailer_events",
    ),
]
