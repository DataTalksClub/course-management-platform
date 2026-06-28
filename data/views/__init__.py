"""Compatibility exports for old `data.views` imports.

Live API/export views are owned by `api.views`.
"""

from api.views.course_exports import course_criteria_yaml_view
from api.views.enrollment_exports import (
    bulk_update_enrollment_certificates_view,
    graduates_data_view,
)
from api.views.health import health_view
from api.views.homework_exports import homework_data_view
from api.views.leaderboard_exports import leaderboard_data_view
from api.views.project_exports import project_data_view
from api.views.webhooks import datamailer_event_webhook

__all__ = [
    "homework_data_view",
    "project_data_view",
    "course_criteria_yaml_view",
    "bulk_update_enrollment_certificates_view",
    "graduates_data_view",
    "health_view",
    "leaderboard_data_view",
    "datamailer_event_webhook",
]
