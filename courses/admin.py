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
        field_styles = "border bg-white font-medium rounded-md shadow-sm text-gray-500 text-sm focus:ring focus:ring-primary-300 focus:border-primary-600 focus:outline-none group-[.errors]:border-red-600 group-[.errors]:focus:ring-red-200 dark:bg-gray-900 dark:border-gray-700 dark:text-gray-400 dark:focus:border-primary-600 dark:focus:ring-primary-700 dark:focus:ring-opacity-50 dark:group-[.errors]:border-red-500 dark:group-[.errors]:focus:ring-red-600/40 px-3 py-2 w-full"
        widgets = {
            "text": forms.TextInput(attrs={"size": "60", 'class': field_styles}),
            "possible_answers": forms.Textarea(attrs={"cols": 60, "rows": 4, 'class': field_styles}),
            "correct_answer": forms.TextInput(attrs={"size": "20", 'class': field_styles}),
        }
        
    
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
