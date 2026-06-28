from .courses import courses_list_view, course_detail_view
from .course_exports import course_criteria_yaml_view
from .enrollment_exports import (
    bulk_update_enrollment_certificates_view,
    graduates_data_view,
)
from .health import health_view
from .homeworks import (
    homeworks_view,
    homework_detail_view,
    homework_detail_by_slug_view,
    homework_score_view,
    homework_score_by_slug_view,
)
from .homework_exports import homework_data_view
from .leaderboard_exports import leaderboard_data_view
from .projects import (
    projects_view,
    project_detail_view,
    project_detail_by_slug_view,
    project_assign_reviews_view,
    project_assign_reviews_by_slug_view,
    project_score_view,
    project_score_by_slug_view,
)
from .project_exports import project_data_view
from .questions import questions_view, question_detail_view
from .registration_campaigns import (
    registration_campaign_detail_view,
    registration_campaign_registrations_view,
    registration_campaigns_view,
)
from .webhooks import datamailer_event_webhook

__all__ = [
    "courses_list_view",
    "course_detail_view",
    "course_criteria_yaml_view",
    "bulk_update_enrollment_certificates_view",
    "graduates_data_view",
    "health_view",
    "homeworks_view",
    "homework_detail_view",
    "homework_detail_by_slug_view",
    "homework_score_view",
    "homework_score_by_slug_view",
    "homework_data_view",
    "leaderboard_data_view",
    "projects_view",
    "project_detail_view",
    "project_detail_by_slug_view",
    "project_assign_reviews_view",
    "project_assign_reviews_by_slug_view",
    "project_score_view",
    "project_score_by_slug_view",
    "project_data_view",
    "questions_view",
    "question_detail_view",
    "registration_campaigns_view",
    "registration_campaign_detail_view",
    "registration_campaign_registrations_view",
    "datamailer_event_webhook",
]
