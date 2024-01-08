from django import forms
from django.contrib import admin
from django.contrib import messages


from .models import Course, Homework, Question, Project

from .scoring import score_homework_submissions


admin.site.register(Course)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "text": forms.TextInput(attrs={"size": "60"}),
            "possible_answers": forms.TextInput(attrs={"size": "30"}),
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


class HomeworkAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    actions = [score_selected_homeworks]


admin.site.register(Homework, HomeworkAdmin)

admin.site.register(Project)
