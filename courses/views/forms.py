from django import forms

from courses.models import (
    Answer,
    CourseRegistration,
    Enrollment,
    LeaderboardComplaint,
)
from courses.registration import region_for_country


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
            "display_on_leaderboard",
            "display_public_profile",
        ]
        widgets = {
            "display_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "display_public_profile": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
            "display_on_leaderboard": forms.CheckboxInput(
                attrs={"class": "h-4 w-4"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.enrollment_certificate_name = self.instance.certificate_name
        if self.user is not None and not self.is_bound:
            self.initial["certificate_name"] = self.user.certificate_name

    def _save_enrollment(self, commit):
        enrollment = super().save(commit=False)
        enrollment.certificate_name = self.enrollment_certificate_name

        if commit:
            enrollment.save()
            self.save_m2m()
        return enrollment

    def _submitted_certificate_name(self):
        return self.cleaned_data.get("certificate_name") or None

    def _sync_user_certificate_name(self, commit):
        if self.user is None:
            return

        certificate_name = self._submitted_certificate_name()
        if self.user.certificate_name == certificate_name:
            return

        self.user.certificate_name = certificate_name
        if commit:
            self.user.save(update_fields=["certificate_name"])

    def save(self, commit=True):
        enrollment = self._save_enrollment(commit)
        self._sync_user_certificate_name(commit)
        return enrollment

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            field_names = self.fields
            for field in field_names:
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


class CourseRegistrationForm(forms.ModelForm):
    accepted_newsletter = forms.BooleanField(
        label=(
            "I agree to be added to the DataTalks.Club newsletter and "
            "receive course updates."
        ),
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
    )

    class Meta:
        model = CourseRegistration
        fields = [
            "email",
            "name",
            "country",
            "role",
            "comment",
            "accepted_newsletter",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.Select(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-control"}),
            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Anything you would like to add?",
                }
            ),
        }

    def __init__(self, *args, campaign=None, user=None, **kwargs):
        self.campaign = campaign
        self.user = user
        super().__init__(*args, **kwargs)
        self.configure_optional_fields()
        self.configure_country_field()
        self.configure_role_choices()
        self.configure_authenticated_user()

    def configure_optional_fields(self):
        optional_field_names = ("name", "country", "role", "comment")
        for field_name in optional_field_names:
            self.fields[field_name].required = False

    def configure_country_field(self):
        self.fields["country"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "country-name",
                "placeholder": "Start typing your country",
                "data-country-combobox-input": "",
            }
        )

    def configure_role_choices(self):
        self.fields["role"].choices = [
            ("", "Select role")
        ] + list(CourseRegistration.Role.choices)

    def has_authenticated_user(self):
        return self.user is not None and self.user.is_authenticated

    def configure_authenticated_email_field(self):
        self.fields["email"].initial = self.user.email
        self.fields["email"].disabled = True
        self.fields["email"].help_text = "Using your account email."

    def authenticated_user_initial_values(self):
        return {
            "name": (
                self.user.certificate_name
                or self.user.get_full_name()
                or ""
            ),
            "country": self.user.country,
            "role": self.user.registration_role,
        }

    def configure_authenticated_user(self):
        if not self.has_authenticated_user():
            return

        self.configure_authenticated_email_field()
        if not self.is_bound:
            self.initial.update(self.authenticated_user_initial_values())

    def clean_email(self):
        if self.user is not None and self.user.is_authenticated:
            email = self.user.email
        else:
            email = self.cleaned_data["email"]

        email_normalized = (email or "").strip().lower()
        if CourseRegistration.objects.filter(
            campaign=self.campaign,
            email_normalized=email_normalized,
        ).exists():
            raise forms.ValidationError(
                "You have already registered for this course."
            )
        return email_normalized

    def clean_country(self):
        country = self.cleaned_data["country"]
        if not country:
            return ""
        if not region_for_country(country):
            raise forms.ValidationError("Select a valid country.")
        return country

    def clean_accepted_newsletter(self):
        accepted_newsletter = self.cleaned_data["accepted_newsletter"]
        if not accepted_newsletter:
            raise forms.ValidationError("This field is required.")
        return accepted_newsletter

    def save(self, commit=True):
        registration = super().save(commit=False)
        registration.campaign = self.campaign
        registration.course = self.campaign.current_course
        registration.region = region_for_country(registration.country)
        if self.user is not None and self.user.is_authenticated:
            registration.user = self.user
            registration.email = self.user.email
        if commit:
            registration.save()
            self.save_user_profile(registration)
        return registration

    def save_user_profile(self, registration):
        if not _can_update_registration_user_profile(self.user):
            return

        update_fields = _update_user_profile_from_registration(
            self.user,
            registration,
        )
        if update_fields:
            self.user.save(update_fields=update_fields)


def _can_update_registration_user_profile(user):
    return user is not None and user.is_authenticated


def _update_user_profile_from_registration(user, registration):
    update_fields = []
    profile_values = _registration_profile_values(registration)
    for field_name, value in profile_values:
        _update_user_profile_field(user, update_fields, field_name, value)
    return update_fields


def _registration_profile_values(registration):
    return (
        ("certificate_name", registration.name.strip()),
        ("country", registration.country),
        ("region", registration.region),
        ("registration_role", registration.role),
    )


def _update_user_profile_field(user, update_fields, field_name, value):
    if not value or getattr(user, field_name) == value:
        return

    setattr(user, field_name, value)
    update_fields.append(field_name)
