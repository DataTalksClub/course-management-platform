from django import forms

from .models import Answer, Enrollment, ProjectSubmission


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["answer_text"]


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["display_name", "certificate_name", "display_on_leaderboard"]


class ProjectSubmissionForm(forms.ModelForm):

    def disable_fields(self):
        for field in self.fields.values():
            field.disabled = True

    class Meta:
        model = ProjectSubmission
        fields = ['github_link', 'commit_id', 'learning_in_public_links', 'faq_contribution', 'time_spent', 'comment']
        widgets = {
            'learning_in_public_links': forms.Textarea(attrs={'rows': 4}),
            'faq_contribution': forms.Textarea(attrs={'rows': 4}),
            'comment': forms.Textarea(attrs={'rows': 4}),
        }