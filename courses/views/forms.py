from django import forms

from courses.models import Answer, Enrollment


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["answer_text"]


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["display_name", "certificate_name"]