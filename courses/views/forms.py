from django import forms

from courses.models import Answer, Enrollment


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["answer_text"]


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = [
            "display_name",
            "certificate_name",
            "github_url",
            "linkedin_url",
            "personal_website_url",
            "about_me",
        ]
        widgets = {
            "display_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "certificate_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "github_url": forms.TextInput(
                attrs={"class": "form-control", "optional": True}
            ),
            "linkedin_url": forms.TextInput(
                attrs={"class": "form-control", "optional": True}
            ),
            "personal_website_url": forms.TextInput(
                attrs={"class": "form-control", "optional": True}
            ),
            "about_me": forms.Textarea(
                attrs={
                    "rows": 3,
                    "style": "height: 100px;",
                    "class": "form-control",
                    "optional": True,
                }
            ),
        }

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            for field in self.fields:
                if field in self.errors:
                    attrs = self.fields[field].widget.attrs
                    class_name = attrs.get("class", "")
                    attrs["class"] = class_name + " is-invalid"
        return valid
