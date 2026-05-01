from django import forms

from courses.models import Answer, Enrollment, LeaderboardComplaint


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["answer_text"]


class EnrollmentForm(forms.ModelForm):
    certificate_name = forms.CharField(
        label="Certificate name",
        required=False,
        help_text="Used for certificates across your course enrollments.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your name for certificates",
            }
        ),
    )

    class Meta:
        model = Enrollment
        fields = [
            "display_name",
            "certificate_name",
            "display_public_profile",
        ]
        widgets = {
            "display_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "display_public_profile": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.enrollment_certificate_name = self.instance.certificate_name
        if self.user is not None and not self.is_bound:
            self.initial["certificate_name"] = self.user.certificate_name

    def save(self, commit=True):
        enrollment = super().save(commit=False)
        enrollment.certificate_name = self.enrollment_certificate_name

        if commit:
            enrollment.save()
            self.save_m2m()

        if self.user is not None:
            certificate_name = self.cleaned_data.get("certificate_name") or None
            if self.user.certificate_name != certificate_name:
                self.user.certificate_name = certificate_name
                if commit:
                    self.user.save(update_fields=["certificate_name"])
        return enrollment

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            for field in self.fields:
                if field in self.errors:
                    attrs = self.fields[field].widget.attrs
                    class_name = attrs.get("class", "")
                    attrs["class"] = class_name + " is-invalid"
        return valid


class LeaderboardComplaintForm(forms.ModelForm):
    class Meta:
        model = LeaderboardComplaint
        fields = ["issue_type", "description"]
        labels = {
            "issue_type": "What is wrong?",
            "description": "Describe the issue",
        }
        widgets = {
            "issue_type": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Include the homework, project, or link that looks "
                        "incorrect and why it should be reviewed."
                    ),
                }
            ),
        }
