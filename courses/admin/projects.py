from django.contrib import admin
from unfold.admin import ModelAdmin

from django.contrib import messages

from courses.models import Project, ReviewCriteria

from courses.projects import (
    assign_peer_reviews_for_project,
    score_project,
    ProjectActionStatus,
)


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


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    actions = [
        assign_peer_reviews_for_project_admin,
        score_projects_admin,
    ]

    list_display = ["title", "course", "state"]
    list_filter = ["course__slug"]


@admin.register(ReviewCriteria)
class ReviewCriteriaAdmin(ModelAdmin):
    pass
