from django import forms
from django.contrib import admin
from django.contrib import messages


from .models import (
    Course,
    Homework,
    Question,
    Project,
    ReviewCriteria,
)

from .scoring import (
    score_homework_submissions,
    update_leaderboard,
    fill_correct_answers,
)

from .projects import (
    assign_peer_reviews_for_project,
    ProjectActionStatus,
)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "text": forms.TextInput(attrs={"size": "60"}),
            "possible_answers": forms.Textarea(
                attrs={"cols": 60, "rows": 4}
            ),
            "correct_answer": forms.TextInput(attrs={"size": "20"}),
        }


class QuestionInline(admin.TabularInline):  # or admin.StackedInline
    model = Question
    form = QuestionForm
    extra = 0


def score_selected_homeworks(modeladmin, request, queryset):
    for homework in queryset:
        status, message = score_homework_submissions(homework.id)
        if status:
            modeladmin.message_user(
                request, message, level=messages.SUCCESS
            )
        else:
            modeladmin.message_user(
                request, message, level=messages.WARNING
            )


score_selected_homeworks.short_description = "Score selected homeworks"


def set_most_popular_as_correct(modeladmin, request, queryset):
    for homework in queryset:
        fill_correct_answers(homework)
        modeladmin.message_user(
            request,
            f"Correct answer for {homework} set to most popular",
            level=messages.SUCCESS,
        )


set_most_popular_as_correct.short_description = (
    "Set correct answers to most popular"
)


class HomeworkAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    actions = [score_selected_homeworks, set_most_popular_as_correct]


admin.site.register(Homework, HomeworkAdmin)


def update_leaderboard_admin(modeladmin, request, queryset):
    for course in queryset:
        update_leaderboard(course)
        modeladmin.message_user(
            request,
            f"Leaderboard updated for course {course}",
            level=messages.SUCCESS,
        )


update_leaderboard_admin.short_description = "Update leaderboard"


class CriteriaForm(forms.ModelForm):
    class Meta:
        model = ReviewCriteria
        fields = "__all__"
        widgets = {
            "description": forms.TextInput(attrs={"size": "60"}),
            "options": forms.Textarea(
                attrs={"cols": 60, "rows": 4}
            )
        }

class CriteriaInline(admin.TabularInline):
    model = ReviewCriteria
    extra = 0

class CourseAdmin(admin.ModelAdmin):
    inlines = [CriteriaInline]
    actions = [update_leaderboard_admin]


admin.site.register(Course, CourseAdmin)


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


class ProjectAdmin(admin.ModelAdmin):
    actions = [assign_peer_reviews_for_project_admin]


admin.site.register(Project, ProjectAdmin)


admin.site.register(ReviewCriteria)
