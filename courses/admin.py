from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from django.contrib import messages


from .models import Course, Homework, Question, Project

from .scoring import score_homework_submissions


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    important_fields = ["title", "social_media_hashtag"]
    list_display = important_fields
    list_filter = important_fields
    search_fields = important_fields


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    important_fields = [
        "course",
        "title",
        "submission_due_date",
        "learning_in_public_cap_project",
        "peer_review_due_date",
        "state",
    ]
    list_display = important_fields
    list_filter = important_fields
    search_fields = important_fields


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"


class QuestionInline(TabularInline):
    model = Question
    form = QuestionForm
    extra = 0


def score_selected_homeworks(modeladmin, request, queryset):
    for homework in queryset:
        status, message = score_homework_submissions(homework.id)
        if status:
            modeladmin.message_user(request, message, level=messages.SUCCESS)
        else:
            modeladmin.message_user(request, message, level=messages.WARNING)


score_selected_homeworks.short_description = "Score selected homeworks"


@admin.register(Homework)
class HomeworkAdmin(ModelAdmin):
    inlines = [QuestionInline]
    actions = [score_selected_homeworks]
    important_fields = ["course", "title", "due_date", "is_scored"]
    list_display = important_fields
    list_filter = important_fields
    search_fields = important_fields
