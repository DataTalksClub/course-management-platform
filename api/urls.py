from django.urls import path

from .openapi.spec import openapi_json_view
from .views import course_exports
from .views import courses
from .views import datamailer_send_audits
from .views import enrollment_certificates
from .views import enrollment_graduates
from .views import health
from .views import homework_exports
from .views import homeworks
from .views import leaderboard_exports
from .views import project_exports
from .views import projects
from .views import questions
from .views import registration_campaigns
from .views import webhooks

urlpatterns = [
    path(
        "openapi.json",
        openapi_json_view,
        name="api_openapi_json",
    ),
    # Public/export endpoints
    path(
        "health/",
        health.health_view,
        name="api_health",
    ),
    path(
        "courses/<slug:course_slug>/course-criteria.yaml",
        course_exports.course_criteria_yaml_view,
        name="api_course_criteria_yaml",
    ),
    path(
        "courses/<slug:course_slug>/leaderboard.yaml",
        leaderboard_exports.leaderboard_data_view,
        name="api_course_leaderboard",
    ),
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
        enrollment_graduates.graduates_data_view,
        name="api_course_graduates",
    ),
    path(
        "courses/<slug:course_slug>/certificates",
        enrollment_certificates.bulk_update_enrollment_certificates_view,
        name="api_course_certificates",
    ),
    path(
        "datamailer/events",
        webhooks.datamailer_event_webhook,
        name="api_datamailer_events",
    ),
    path(
        "datamailer/send-audits",
        datamailer_send_audits.datamailer_send_audits_view,
        name="api_datamailer_send_audits",
    ),
    # Courses
    path(
        "courses/",
        courses.courses_list_view,
        name="api_courses_list",
    ),
    path(
        "courses/<slug:course_slug>/",
        courses.course_detail_view,
        name="api_course_detail",
    ),
    path(
        "registration-campaigns/",
        registration_campaigns.registration_campaigns_view,
        name="api_registration_campaigns",
    ),
    path(
        "registration-campaigns/<slug:campaign_slug>/",
        registration_campaigns.registration_campaign_detail_view,
        name="api_registration_campaign_detail",
    ),
    path(
        "registration-campaigns/<slug:campaign_slug>/registrations/",
        registration_campaigns.registration_campaign_registrations_view,
        name="api_registration_campaign_registrations",
    ),
    # Homeworks
    path(
        "courses/<slug:course_slug>/homeworks/",
        homeworks.homeworks_view,
        name="api_homeworks",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/",
        homeworks.homework_detail_view,
        name="api_homework_detail",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/score/",
        homeworks.homework_score_view,
        name="api_homework_score",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/by-slug/<slug:homework_slug>/",
        homeworks.homework_detail_by_slug_view,
        name="api_homework_detail_by_slug",
    ),
    path(
        "courses/<slug:course_slug>/homeworks/by-slug/<slug:homework_slug>/score/",
        homeworks.homework_score_by_slug_view,
        name="api_homework_score_by_slug",
    ),
    # Projects
    path(
        "courses/<slug:course_slug>/projects/",
        projects.projects_view,
        name="api_projects",
    ),
    path(
        "courses/<slug:course_slug>/projects/<int:project_id>/",
        projects.project_detail_view,
        name="api_project_detail",
    ),
    path(
        "courses/<slug:course_slug>/projects/<int:project_id>/assign-reviews/",
        projects.project_assign_reviews_view,
        name="api_project_assign_reviews",
    ),
    path(
        "courses/<slug:course_slug>/projects/<int:project_id>/score/",
        projects.project_score_view,
        name="api_project_score",
    ),
    path(
        "courses/<slug:course_slug>/projects/by-slug/<slug:project_slug>/",
        projects.project_detail_by_slug_view,
        name="api_project_detail_by_slug",
    ),
    path(
        "courses/<slug:course_slug>/projects/by-slug/<slug:project_slug>/assign-reviews/",
        projects.project_assign_reviews_by_slug_view,
        name="api_project_assign_reviews_by_slug",
    ),
    path(
        "courses/<slug:course_slug>/projects/by-slug/<slug:project_slug>/score/",
        projects.project_score_by_slug_view,
        name="api_project_score_by_slug",
    ),
    # Questions
    path(
        "courses/<slug:course_slug>/homeworks/<int:homework_id>/questions/",
        questions.questions_view,
        name="api_questions",
    ),
    path(
        (
            "courses/<slug:course_slug>/homeworks/<int:homework_id>/"
            "questions/<int:question_id>/"
        ),
        questions.question_detail_view,
        name="api_question_detail",
    ),
]
