from django import forms
from django.contrib import admin
from django.contrib import messages


from .models import Course, Homework, Question, Project

from .scoring import score_homework_submissions, update_leaderboard



class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "text": forms.TextInput(attrs={"size": "60"}),
            "possible_answers": forms.Textarea(attrs={"cols": 60, "rows": 4}),
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


score_selected_homeworks.short_description = (
    "Score selected homeworks"
)


def update_leaderboard_admin(modeladmin, request, queryset):
    for course in queryset:
        update_leaderboard(course)
        modeladmin.message_user(
            request,
            f"Leaderboard updated for course {course}",
            level=messages.SUCCESS,
        )

update_leaderboard_admin.short_description = "Update leaderboard"


class HomeworkAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    actions = [score_selected_homeworks]

admin.site.register(Homework, HomeworkAdmin)


class CourseAdmin(admin.ModelAdmin):
    actions = [update_leaderboard_admin]

admin.site.register(Course, CourseAdmin)

admin.site.register(Project)
