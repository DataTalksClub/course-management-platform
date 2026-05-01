from django import forms

from accounts.models import CustomUser


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            "certificate_name",
            "github_url",
            "linkedin_url",
            "personal_website_url",
            "about_me",
            "dark_mode",
        ]
        labels = {
            "certificate_name": "Certificate name",
            "github_url": "GitHub URL",
            "linkedin_url": "LinkedIn URL",
            "personal_website_url": "Website URL",
            "about_me": "About me",
            "dark_mode": "Use dark mode",
        }
        help_texts = {
            "certificate_name": (
                "Used for certificates across your course enrollments."
            ),
        }
        widgets = {
            "certificate_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your name for certificates",
                }
            ),
            "github_url": forms.TextInput(attrs={"class": "form-control"}),
            "linkedin_url": forms.TextInput(attrs={"class": "form-control"}),
            "personal_website_url": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "about_me": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "style": "height: 100px;",
                }
            ),
            "dark_mode": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }
