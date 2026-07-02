from django import forms

from accounts.models import CustomUser
from accounts.services.timezones import build_timezone_options, is_valid_timezone


PREFERRED_TIMEZONE_WIDGET = forms.Select(attrs={"class": "form-control"})
CERTIFICATE_NAME_WIDGET = forms.TextInput(
    attrs={
        "class": "form-control",
        "placeholder": "Your name for certificates",
    }
)
COUNTRY_WIDGET = forms.TextInput(
    attrs={
        "class": "form-control",
        "placeholder": "Your country",
    }
)
REGISTRATION_ROLE_WIDGET = forms.TextInput(
    attrs={
        "class": "form-control",
        "placeholder": "Your role",
    }
)
GITHUB_URL_WIDGET = forms.TextInput(attrs={"class": "form-control"})
LINKEDIN_URL_WIDGET = forms.TextInput(attrs={"class": "form-control"})
PERSONAL_WEBSITE_URL_WIDGET = forms.TextInput(
    attrs={"class": "form-control"}
)
ABOUT_ME_WIDGET = forms.Textarea(
    attrs={
        "class": "form-control",
        "rows": 3,
        "style": "height: 100px;",
    }
)
DARK_MODE_WIDGET = forms.CheckboxInput(attrs={"class": "h-4 w-4"})


class AccountSettingsForm(forms.ModelForm):
    preferred_timezone = forms.ChoiceField(
        required=False,
        choices=[],
        widget=PREFERRED_TIMEZONE_WIDGET,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        timezone_choices = [("", "UTC until your browser timezone is detected")]
        for option in build_timezone_options():
            timezone_choice = (option.value, option.label)
            timezone_choices.append(timezone_choice)
        self.fields["preferred_timezone"].choices = timezone_choices

    def clean_preferred_timezone(self):
        timezone_name = self.cleaned_data.get("preferred_timezone", "")
        if timezone_name and not is_valid_timezone(timezone_name):
            raise forms.ValidationError("Choose a valid timezone.")
        return timezone_name

    class Meta:
        model = CustomUser
        fields = [
            "certificate_name",
            "country",
            "registration_role",
            "github_url",
            "linkedin_url",
            "personal_website_url",
            "about_me",
            "preferred_timezone",
            "dark_mode",
        ]
        labels = {
            "certificate_name": "Certificate name",
            "country": "Country",
            "registration_role": "Role",
            "github_url": "GitHub URL",
            "linkedin_url": "LinkedIn URL",
            "personal_website_url": "Website URL",
            "about_me": "About me",
            "preferred_timezone": "Timezone",
            "dark_mode": "Use dark mode",
        }
        help_texts = {
            "certificate_name": (
                "Used for certificates across your course enrollments."
            ),
            "country": "Used to prefill course registration forms.",
            "registration_role": "Used to prefill course registration forms.",
            "preferred_timezone": (
                "Used to render deadlines and notification emails. We detect "
                "your browser timezone automatically, and you can override it."
            ),
        }
        widgets = {
            "certificate_name": CERTIFICATE_NAME_WIDGET,
            "country": COUNTRY_WIDGET,
            "registration_role": REGISTRATION_ROLE_WIDGET,
            "github_url": GITHUB_URL_WIDGET,
            "linkedin_url": LINKEDIN_URL_WIDGET,
            "personal_website_url": PERSONAL_WEBSITE_URL_WIDGET,
            "about_me": ABOUT_ME_WIDGET,
            "dark_mode": DARK_MODE_WIDGET,
        }
