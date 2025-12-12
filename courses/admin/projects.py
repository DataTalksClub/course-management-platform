from django.contrib import admin
from unfold.admin import ModelAdmin

from django.contrib import messages

from courses.mixin import InstructorAccessMixin
from courses.models import Project, ReviewCriteria, ProjectState

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
class ProjectAdmin(InstructorAccessMixin, ModelAdmin):
    actions = [
        assign_peer_reviews_for_project_admin,
        score_projects_admin,
        calculate_statistics_selected_projects,
    ]

    list_display = ["title", "course", "state"]
    list_filter = ["course__slug"]

    instructor_field = "course__instructor"


@admin.register(ReviewCriteria)
class ReviewCriteriaAdmin(InstructorAccessMixin, ModelAdmin):
    list_display = ["course", "description", "review_criteria_type"]
    list_filter = ["course"]

    instructor_field = "course__instructor"
