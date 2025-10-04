from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import (
    UnfoldAdminTextInputWidget,
    UnfoldAdminTextareaWidget,
)
from django.contrib import messages

from courses.mixin import InstructorAccessMixin
from courses.models import Homework, Question, HomeworkState

from courses.scoring import (
    score_homework_submissions,
    fill_correct_answers,
    calculate_homework_statistics,
)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "text": UnfoldAdminTextInputWidget(attrs={"size": "60"}),
            "possible_answers": UnfoldAdminTextareaWidget(
                attrs={"cols": 60, "rows": 4}
            ),
            "correct_answer": UnfoldAdminTextInputWidget(
                attrs={"size": "20"}
            ),
        }


class QuestionInline(TabularInline):
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


def calculate_statistics_selected_homeworks(
    modeladmin, request, queryset
):
    for homework in queryset:
        if homework.state != HomeworkState.SCORED.value:
            modeladmin.message_user(
                request,
                f"Cannot calculate statistics for {homework} "
                "because it has not been scored",
                level=messages.WARNING,
            )
            continue

        calculate_homework_statistics(homework, force=True)

        message = f"Statistics calculated for {homework}"
        modeladmin.message_user(
            request, message, level=messages.SUCCESS
        )


calculate_statistics_selected_homeworks.short_description = (
    "Calculate statistics"
)


@admin.register(Homework)
class HomeworkAdmin(InstructorAccessMixin, ModelAdmin):
    inlines = [QuestionInline]
    actions = [
        score_selected_homeworks,
        set_most_popular_as_correct,
        calculate_statistics_selected_homeworks,
    ]
    list_display = ["title", "course", "due_date", "state"]
    list_filter = ["course__slug"]

    instructor_field = "course__instructor"
