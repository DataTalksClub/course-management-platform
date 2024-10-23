from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import (
    UnfoldAdminTextInputWidget,
    UnfoldAdminTextareaWidget,
)

from django.contrib import messages

from courses.models import Course, ReviewCriteria
from courses.scoring import update_leaderboard


class CriteriaForm(forms.ModelForm):
    class Meta:
        model = ReviewCriteria
        fields = "__all__"
        widgets = {
            "description": UnfoldAdminTextInputWidget(
                attrs={"size": "60"}
            ),
            "options": UnfoldAdminTextareaWidget(
                attrs={"cols": 60, "rows": 4}
            ),
        }


class CriteriaInline(TabularInline):
    model = ReviewCriteria
    form = CriteriaForm
    extra = 0


def update_leaderboard_admin(modeladmin, request, queryset):
    for course in queryset:
        update_leaderboard(course)
        modeladmin.message_user(
            request,
            f"Leaderboard updated for course {course}",
            level=messages.SUCCESS,
        )


update_leaderboard_admin.short_description = "Update leaderboard"


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    actions = [update_leaderboard_admin]
    inlines = [CriteriaInline]
    list_display = ["title"]
