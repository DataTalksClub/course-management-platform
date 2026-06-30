"""
Compatibility URL module for legacy imports.

The live `/api/` routes are registered from `api.urls`. Keep this module only
while external code may still import `data.urls` directly.
"""

from django.urls import path

from api.views import course_exports
from api.views import enrollment_exports
from api.views import health
from api.views import homework_exports
from api.views import leaderboard_exports
from api.views import project_exports
from api.views import webhooks


urlpatterns = [
    # Health check (public, no auth required)
    path(
        "health/",
        health.health_view,
        name="api_health",
    ),
    # Course criteria (public, no auth required)
    path(
        "courses/<slug:course_slug>/course-criteria.yaml",
        course_exports.course_criteria_yaml_view,
        name="api_course_criteria_yaml",
    ),
    # Leaderboard data (public, no auth required)
    path(
        "courses/<slug:course_slug>/leaderboard.yaml",
        leaderboard_exports.leaderboard_data_view,
        name="api_course_leaderboard",
    ),
    # Data API endpoints (require auth)
    path(
        "courses/<slug:course_slug>/homeworks/<slug:homework_slug>/submissions",
        homework_exports.homework_data_view,
        name="api_homework_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/projects/<slug:project_slug>/submissions",
        project_exports.project_data_view,
        name="api_project_submissions_export",
    ),
    path(
        "courses/<slug:course_slug>/graduates",
        enrollment_exports.graduates_data_view,
        name="api_course_graduates",
    ),
    path(
        "courses/<slug:course_slug>/certificates",
        enrollment_exports.bulk_update_enrollment_certificates_view,
        name="api_course_certificates",
    ),
    path(
        "datamailer/events",
        webhooks.datamailer_event_webhook,
        name="api_datamailer_events",
    ),
]
