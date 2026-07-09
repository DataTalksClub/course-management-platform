from django.urls import path

from .views import campaigns
from .views import course_admin
from .views import datamailer
from .views import enrollment
from .views import homework
from .views import observability
from .views import projects

urlpatterns = [
    path("", course_admin.course_list, name="cadmin_course_list"),
    path(
        "campaigns/new/",
        campaigns.campaign_create,
        name="cadmin_campaign_create",
    ),
    path(
        "campaigns/<slug:campaign_slug>/edit/",
        campaigns.campaign_edit,
        name="cadmin_campaign_edit",
    ),
    path(
        "registrations/<slug:campaign_slug>/",
        campaigns.campaign_registrations,
        name="cadmin_campaign_registrations",
    ),
    path(
        "datamailer/",
        datamailer.datamailer_operations,
        name="cadmin_datamailer_operations",
    ),
    path(
        "datamailer/events/",
        datamailer.datamailer_events,
        name="cadmin_datamailer_events",
    ),
    path(
        "cloudwatch/",
        observability.cloudwatch_dashboard,
        name="cadmin_cloudwatch_dashboard",
    ),
    path(
        "<slug:course_slug>/",
        course_admin.course_admin,
        name="cadmin_course",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/score",
        homework.homework_score,
        name="cadmin_homework_score",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/notify-scores",
        homework.homework_notify_scores,
        name="cadmin_homework_notify_scores",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/set-correct-answers",
        homework.homework_set_correct_answers,
        name="cadmin_homework_set_correct_answers",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/clear-correct-answers",
        homework.homework_clear_correct_answers,
        name="cadmin_homework_clear_correct_answers",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/submissions",
        homework.homework_submissions,
        name="cadmin_homework_submissions",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/submissions/<int:submission_id>/edit",
        homework.homework_submission_edit,
        name="cadmin_homework_submission_edit",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/assign-reviews",
        projects.project_assign_reviews,
        name="cadmin_project_assign_reviews",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/score",
        projects.project_score,
        name="cadmin_project_score",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/submissions",
        projects.project_submissions,
        name="cadmin_project_submissions",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>/submissions/<int:submission_id>/edit",
        projects.project_submission_edit,
        name="cadmin_project_submission_edit",
    ),
    path(
        "<slug:course_slug>/enrollments/",
        enrollment.enrollments_list,
        name="cadmin_enrollments",
    ),
    path(
        "<slug:course_slug>/leaderboard-complaints/",
        enrollment.leaderboard_complaints,
        name="cadmin_leaderboard_complaints",
    ),
    path(
        "<slug:course_slug>/leaderboard-complaints/<int:complaint_id>/resolve",
        enrollment.leaderboard_complaint_resolve,
        name="cadmin_leaderboard_complaint_resolve",
    ),
    path(
        "<slug:course_slug>/enrollment/<int:enrollment_id>/edit",
        enrollment.enrollment_edit,
        name="cadmin_enrollment_edit",
    ),
]
