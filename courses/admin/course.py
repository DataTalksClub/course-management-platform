from django import forms
from django.contrib import admin
from django.utils import timezone
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


def duplicate_course(modeladmin, request, queryset):
    current_year = timezone.now().year

    for course in queryset:
        # Create a new course instance
        old_title = course.title
        new_title = old_title.replace(
            str(current_year - 1), str(current_year)
        )
        if str(current_year - 1) not in old_title:
            new_title = f"{old_title} {current_year}"

        old_slug = course.slug
        new_slug = old_slug.replace(
            str(current_year - 1), str(current_year)
        )
        if str(current_year - 1) not in old_slug:
            new_slug = f"{old_slug}-{current_year}"

        # Create new course with updated fields
        new_course = Course.objects.create(
            title=new_title,
            slug=new_slug,
            description=course.description,
            social_media_hashtag=course.social_media_hashtag,
            first_homework_scored=False,
            finished=False,
            faq_document_url=course.faq_document_url,
        )

        # Copy review criteria with all fields
        for criteria in course.reviewcriteria_set.all():
            ReviewCriteria.objects.create(
                course=new_course,
                description=criteria.description,
                options=criteria.options,
                review_criteria_type=criteria.review_criteria_type,
            )

        modeladmin.message_user(
            request,
            f"Course '{old_title}' was duplicated to '{new_title}'",
            level=messages.SUCCESS,
        )


duplicate_course.short_description = "Duplicate selected courses"


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    actions = [update_leaderboard_admin, duplicate_course]
    inlines = [CriteriaInline]
    list_display = ["title"]
