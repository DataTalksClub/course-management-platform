from django import forms
from django.contrib import admin

from .models import Course
from .models import Homework, Question

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


class HomeworkAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]


admin.site.register(Homework, HomeworkAdmin)