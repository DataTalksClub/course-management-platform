from django import forms

from courses.models import Answer, Enrollment, CourseRegistration
from courses.constants import COUNTRIES, ROLE_CHOICES


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["answer_text"]


class CourseRegistrationForm(forms.ModelForm):
    """Form for course registration on the landing page"""
    
    country = forms.ChoiceField(
        choices=[("", "Select your country")] + [(country, country) for country, _ in COUNTRIES],
        widget=forms.Select(attrs={"class": "form-control"}),
        required=True,
    )
    
    role = forms.ChoiceField(
        choices=[("", "Select your role")] + ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        required=True,
    )
    
    class Meta:
        model = CourseRegistration
        fields = ["email", "name", "country", "role", "comment"]
        widgets = {
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "your.email@example.com"}
            ),
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Your Full Name"}
            ),
            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Anything you would like to add? (optional)",
                }
            ),
        }
        labels = {
            "email": "Email",
            "name": "Name",
            "country": "Country",
            "role": "What best describes you?",
            "comment": "Comment",
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If user is authenticated, pre-fill and lock the email field
        if user and user.is_authenticated:
            self.fields["email"].initial = user.email
            self.fields["email"].widget.attrs["readonly"] = True
            
        # Make comment optional
        self.fields["comment"].required = False


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
