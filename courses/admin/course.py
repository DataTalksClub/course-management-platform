from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import (
    UnfoldAdminTextInputWidget,
    UnfoldAdminTextareaWidget,
)

from courses.models.course import (
    Course,
    CourseRegistration,
    EmailCampaign,
    LeaderboardComplaint,
    RegistrationCampaign,
)
from courses.models.project import (
    ReviewCriteria,
)
from courses.leaderboard import update_leaderboard
from courses.validators.criteria_validators import (
    validate_review_criteria_options,
)


CRITERIA_DESCRIPTION_WIDGET = UnfoldAdminTextInputWidget(
    attrs={"size": "60"}
)
CRITERIA_OPTIONS_WIDGET = UnfoldAdminTextareaWidget(
    attrs={"cols": 60, "rows": 4}
)


class CriteriaForm(forms.ModelForm):
    class Meta:
        model = ReviewCriteria
        fields = "__all__"
        widgets = {
            "description": CRITERIA_DESCRIPTION_WIDGET,
            "options": CRITERIA_OPTIONS_WIDGET,
        }

    def clean_options(self):
        """Validate the options field to ensure it has the correct structure."""
        options = self.cleaned_data.get("options")

        if options is None:
            raise ValidationError("Options field cannot be empty.")

        try:
            validate_review_criteria_options(options)
        except ValidationError as exc:
            error_messages = getattr(exc, "messages", None)
            if error_messages:
                error_msg = error_messages[0]
            else:
                error_msg = str(exc)

            raise ValidationError(
                f"Invalid options format. {error_msg}\n\n"
                f"Expected format:\n"
                f'[{{"criteria": "Poor", "score": 0}}, '
                f'{{"criteria": "Good", "score": 1}}, ...]'
            ) from exc

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
    duplicate_fields = _course_duplicate_fields(course, current_year)
    new_course = Course.objects.create(**duplicate_fields)
    _copy_review_criteria(course, new_course)
    return new_course


def _course_duplicate_fields(course, current_year):
    title = _year_rollover_value(course.title, current_year, " ")
    slug = _year_rollover_value(course.slug, current_year, "-")
    return {
        "title": title,
        "slug": slug,
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
        "requires_registration_approval": (
            course.requires_registration_approval
        ),
    }


def _year_rollover_value(value, current_year, separator):
    previous_year = str(current_year - 1)
    current_year_text = str(current_year)
    if previous_year in value:
        return value.replace(previous_year, current_year_text)
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
        "requires_registration_approval",
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
    filter_horizontal = ["suggested_campaigns"]
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
            "Cross-sell",
            {
                "fields": [
                    "suggested_campaigns",
                    "exclude_from_suggestions",
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


@admin.register(EmailCampaign)
class EmailCampaignAdmin(ModelAdmin):
    list_display = [
        "subject",
        "registration_campaign",
        "status",
        "last_recipient_count",
        "updated_at",
    ]
    search_fields = ["subject", "external_key"]
    list_filter = ["status", "registration_campaign"]
    readonly_fields = [
        "external_key",
        "created_at",
        "updated_at",
        "queued_at",
        "cancelled_at",
    ]


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(ModelAdmin):
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="Approve selected applications")
    def approve_selected(self, request, queryset):
        from courses.registration_wall import approve_registration

        for registration in queryset.order_by("pk"):
            approve_registration(registration)

    @admin.action(description="Reject selected applications")
    def reject_selected(self, request, queryset):
        for registration in queryset.order_by("pk"):
            registration.status = CourseRegistration.Status.REJECTED
            registration.save(update_fields=["status", "updated_at"])

    list_display = [
        "email_normalized",
        "campaign",
        "course",
        "company_name",
        "country",
        "region",
        "role",
        "status",
        "created_at",
    ]
    search_fields = ["email", "email_normalized", "name", "company_name"]
    list_filter = [
        "campaign",
        "course",
        "region",
        "role",
        "status",
        "source",
    ]
    raw_id_fields = ["referred_by"]
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
                    "company_name",
                    "country",
                    "region",
                    "role",
                    "comment",
                    "accepted_newsletter",
                    "accepted_nebius_sharing",
                    "source",
                    "referred_by",
                ]
            },
        ),
        (
            "Application review",
            {
                "fields": [
                    "status",
                    "experience",
                    "years_experience",
                    "why_join",
                    "linkedin_url",
                    "github_url",
                    "prereq_python",
                    "prereq_docker",
                    "prereq_http",
                    "prereq_cli",
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
