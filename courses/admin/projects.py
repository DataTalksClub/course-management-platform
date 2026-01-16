from django.contrib import admin
from unfold.admin import ModelAdmin

from django.contrib import messages

from courses.models import Project, ReviewCriteria, ProjectState, ProjectSubmission

from courses.projects import (
    assign_peer_reviews_for_project,
    score_project,
    ProjectActionStatus,
)

from courses.scoring import calculate_project_statistics


def assign_peer_reviews_for_project_admin(
    modeladmin, request, queryset
):
    for project in queryset:
        status, message = assign_peer_reviews_for_project(project)
        if status == ProjectActionStatus.OK:
            modeladmin.message_user(
                request, message, level=messages.SUCCESS
            )
        else:
            modeladmin.message_user(
                request, message, level=messages.WARNING
            )


assign_peer_reviews_for_project_admin.short_description = (
    "Assign peer reviews"
)


def score_projects_admin(modeladmin, request, queryset):
    for project in queryset:
        status, message = score_project(project)
        if status == ProjectActionStatus.OK:
            modeladmin.message_user(
                request, message, level=messages.SUCCESS
            )
        else:
            modeladmin.message_user(
                request, message, level=messages.WARNING
            )


score_projects_admin.short_description = "Score projects"


def calculate_statistics_selected_projects(
    modeladmin, request, queryset
):
    for project in queryset:
        if project.state != ProjectState.COMPLETED.value:
            modeladmin.message_user(
                request,
                f"Cannot calculate statistics for {project} "
                "because it has not been completed",
                level=messages.WARNING,
            )
            continue

        calculate_project_statistics(project, force=True)

        message = f"Statistics calculated for {project}"
        modeladmin.message_user(
            request, message, level=messages.SUCCESS
        )


calculate_statistics_selected_projects.short_description = (
    "Calculate statistics"
)


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    actions = [
        assign_peer_reviews_for_project_admin,
        score_projects_admin,
        calculate_statistics_selected_projects,
    ]

    list_display = ["title", "course", "state"]
    list_filter = ["course__slug"]


@admin.register(ReviewCriteria)
class ReviewCriteriaAdmin(ModelAdmin):
    pass


@admin.register(ProjectSubmission)
class ProjectSubmissionAdmin(ModelAdmin):
    """Admin interface for ProjectSubmission to allow editing results after evaluation"""
    
    list_display = [
        "id",
        "student",
        "project",
        "submitted_at",
        "total_score",
        "passed",
    ]
    
    list_filter = ["project__course__slug", "project", "passed"]
    
    search_fields = [
        "student__username",
        "student__email",
        "project__title",
    ]
    
    # Fields that can be edited
    fields = [
        "project",
        "student",
        "enrollment",
        "github_link",
        "commit_id",
        "learning_in_public_links",
        "faq_contribution",
        "time_spent",
        "problems_comments",
        "submitted_at",
        "project_score",
        "project_faq_score",
        "project_learning_in_public_score",
        "peer_review_score",
        "peer_review_learning_in_public_score",
        "total_score",
        "reviewed_enough_peers",
        "passed",
    ]
    
    readonly_fields = ["submitted_at"]
    
    # Allow editing all score fields and pass/fail status
    # This enables manual corrections after the evaluation phase
