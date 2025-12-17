from django.contrib import admin
from django.contrib import messages
from unfold.admin import ModelAdmin

from courses.models.wrapped import (
    WrappedStatistics,
    UserWrappedStatistics,
)
from courses.scoring import calculate_wrapped_statistics


@admin.action(description="Recalculate statistics")
def recalculate_wrapped_stats(modeladmin, request, queryset):
    for wrapped in queryset:
        calculate_wrapped_statistics(year=wrapped.year, force=True)
        modeladmin.message_user(
            request,
            f"Statistics recalculated for {wrapped.year}",
            level=messages.SUCCESS,
        )


@admin.register(WrappedStatistics)
class WrappedStatisticsAdmin(ModelAdmin):
    list_display = (
        "year",
        "is_visible",
        "total_participants",
        "total_enrollments",
        "total_hours",
        "total_certificates",
        "calculated_at",
    )
    list_filter = ("is_visible", "year")
    search_fields = ("year",)
    actions = [recalculate_wrapped_stats]


@admin.register(UserWrappedStatistics)
class UserWrappedStatisticsAdmin(ModelAdmin):
    list_display = (
        "display_name",
        "wrapped__year",
        "rank",
        "total_points",
        "homework_count",
        "project_count",
    )
    list_filter = ("wrapped__year",)
    search_fields = ("display_name", "user__email", "user__username")
    autocomplete_fields = ("user", "wrapped")
