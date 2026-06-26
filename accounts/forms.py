from django import forms

from accounts.models import CustomUser
from accounts.services.timezones import build_timezone_options, is_valid_timezone


class AccountSettingsForm(forms.ModelForm):
    preferred_timezone = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        timezone_choices = [("", "UTC until your browser timezone is detected")]
        timezone_choices += [
            (option.value, option.label) for option in build_timezone_options()
        ]
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
            "email_submission_confirmations",
            "email_deadline_reminders",
            "email_course_updates",
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
            "email_submission_confirmations": (
                "Homework and project submissions"
            ),
            "email_deadline_reminders": "Deadline reminders",
            "email_course_updates": "General course-related emails",
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
            "email_submission_confirmations": (
                "Sends confirmation and score emails after you submit "
                "homework or a project."
            ),
            "email_deadline_reminders": (
                "Sends reminders when homework or peer review deadlines "
                "are within 24 hours and you have not submitted. For "
                "projects, sends one reminder one week before the deadline "
                "encouraging half-finished submissions, and another one "
                "day before the deadline because submissions will close "
                "soon. For peer reviews, sends links to unfinished reviews "
                "and explains that peer review completion is mandatory for "
                "project completion and receiving a certificate."
            ),
            "email_course_updates": (
                "Sends general course and workshop messages, such as "
                "course start announcements and workshop start announcements."
            ),
        }
        widgets = {
            "certificate_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your name for certificates",
                }
            ),
            "country": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your country",
                }
            ),
            "registration_role": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your role",
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
            "email_submission_confirmations": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
            "email_deadline_reminders": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
            "email_course_updates": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
        }
