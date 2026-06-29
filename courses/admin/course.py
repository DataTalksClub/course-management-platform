from django import forms
from django.contrib import admin
from django.utils import timezone
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import (
    UnfoldAdminTextInputWidget,
    UnfoldAdminTextareaWidget,
)

from django.contrib import messages

from courses.models import (
    Course,
    CourseRegistration,
    LeaderboardComplaint,
    RegistrationCampaign,
    ReviewCriteria,
)
from courses.scoring import update_leaderboard
from courses.validators import validate_review_criteria_options


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
    
    def clean_options(self):
        """Validate the options field to ensure it has the correct structure."""
        options = self.cleaned_data.get('options')
        
        if options is None:
            raise ValidationError("Options field cannot be empty.")
        
        # Run the validator
        try:
            validate_review_criteria_options(options)
        except ValidationError as e:
            # Extract error message properly for modern Django
            if hasattr(e, 'messages') and e.messages:
                error_msg = e.messages[0]
            else:
                error_msg = str(e)
            
            raise ValidationError(
                f"Invalid options format. {error_msg}\n\n"
                f"Expected format:\n"
                f'[{{"criteria": "Poor", "score": 0}}, '
                f'{{"criteria": "Good", "score": 1}}, ...]'
            )
        
        return options


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
        new_course = _duplicate_course(course, current_year)
        modeladmin.message_user(
            request,
            f"Course '{course.title}' was duplicated to "
            f"'{new_course.title}'",
            level=messages.SUCCESS,
        )


duplicate_course.short_description = "Duplicate selected courses"


def _duplicate_course(course, current_year):
    new_course = Course.objects.create(
        **_course_duplicate_fields(course, current_year)
    )
    _copy_review_criteria(course, new_course)
    return new_course


def _course_duplicate_fields(course, current_year):
    return {
        "title": _year_rollover_value(course.title, current_year, " "),
        "slug": _year_rollover_value(course.slug, current_year, "-"),
        "description": course.description,
        "start_date": course.start_date,
        "end_date": course.end_date,
        "registration_url": course.registration_url,
        "github_repo_url": course.github_repo_url,
        "social_media_hashtag": course.social_media_hashtag,
        "first_homework_scored": False,
        "finished": False,
        "faq_document_url": course.faq_document_url,
        "project_passing_score": course.project_passing_score,
        "visible": course.visible,
    }


def _year_rollover_value(value, current_year, separator):
    previous_year = str(current_year - 1)
    if previous_year in value:
        return value.replace(previous_year, str(current_year))
    return f"{value}{separator}{current_year}"


def _copy_review_criteria(source_course, target_course):
    review_criteria = source_course.reviewcriteria_set.all()
    for criteria in review_criteria:
        ReviewCriteria.objects.create(
            course=target_course,
            description=criteria.description,
            options=criteria.options,
            review_criteria_type=criteria.review_criteria_type,
        )


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    actions = [update_leaderboard_admin, duplicate_course]
    inlines = [CriteriaInline]
    list_display = [
        "title",
        "start_date",
        "end_date",
        "visible",
        "finished",
    ]


@admin.register(RegistrationCampaign)
class RegistrationCampaignAdmin(ModelAdmin):
    prepopulated_fields = {"slug": ("title",)}
    list_display = [
        "title",
        "slug",
        "current_course",
        "is_active",
    ]
    search_fields = ["title", "slug"]
    list_filter = ["is_active", "current_course"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        (
            "Landing page",
            {
                "fields": [
                    "title",
                    "slug",
                    "edition_label",
                    "current_course",
                    "is_active",
                    "hero_image_url",
                    "video_url",
                    "meta_description",
                    "marketing_markdown",
                ]
            },
        ),
        (
            "Timestamps",
            {
                "classes": ["collapse"],
                "fields": ["created_at", "updated_at"],
            },
        ),
    ]


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(ModelAdmin):
    list_display = [
        "email_normalized",
        "campaign",
        "course",
        "country",
        "region",
        "role",
        "created_at",
    ]
    search_fields = ["email", "email_normalized", "name"]
    list_filter = [
        "campaign",
        "course",
        "region",
        "role",
    ]
    readonly_fields = [
        "email_normalized",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (
            "Registration",
            {
                "fields": [
                    "campaign",
                    "course",
                    "user",
                    "email",
                    "email_normalized",
                    "name",
                    "country",
                    "region",
                    "role",
                    "comment",
                    "accepted_newsletter",
                ]
            },
        ),
        (
            "Timestamps",
            {
                "classes": ["collapse"],
                "fields": ["created_at", "updated_at"],
            },
        ),
    ]


@admin.register(LeaderboardComplaint)
class LeaderboardComplaintAdmin(ModelAdmin):
    list_display = [
        "enrollment",
        "issue_type",
        "resolved",
        "created_at",
        "resolved_at",
    ]
    list_filter = ["resolved", "issue_type", "enrollment__course"]
    search_fields = [
        "description",
        "enrollment__display_name",
        "enrollment__student__email",
        "reporter__email",
    ]
    readonly_fields = ["created_at"]
