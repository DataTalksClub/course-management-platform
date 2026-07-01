from django import forms

from courses.models.course import CourseRegistration
from courses.registration import region_for_country
from courses.views.registration_profile import (
    can_update_registration_user_profile,
    update_user_profile_from_registration,
)


ACCEPTED_NEWSLETTER_WIDGET = forms.CheckboxInput(
    attrs={"class": "h-4 w-4"}
)
EMAIL_WIDGET = forms.EmailInput(attrs={"class": "form-control"})
NAME_WIDGET = forms.TextInput(attrs={"class": "form-control"})
COUNTRY_SELECT_WIDGET = forms.Select(attrs={"class": "form-control"})
ROLE_WIDGET = forms.Select(attrs={"class": "form-control"})
COMMENT_WIDGET = forms.Textarea(
    attrs={
        "class": "form-control",
        "rows": 4,
        "placeholder": "Anything you would like to add?",
    }
)
COUNTRY_COMBOBOX_WIDGET_ATTRS = {
    "class": "form-control",
    "autocomplete": "country-name",
    "placeholder": "Start typing your country",
    "data-country-combobox-input": "",
}


class CourseRegistrationForm(forms.ModelForm):
    accepted_newsletter = forms.BooleanField(
        label=(
            "I agree to be added to the DataTalks.Club newsletter and "
            "receive course updates."
        ),
        required=True,
        widget=ACCEPTED_NEWSLETTER_WIDGET,
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
            "email": EMAIL_WIDGET,
            "name": NAME_WIDGET,
            "country": COUNTRY_SELECT_WIDGET,
            "role": ROLE_WIDGET,
            "comment": COMMENT_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.configure_optional_fields()
        self.configure_country_field()
        self.configure_role_choices()
        self.configure_authenticated_user()

    def configure_optional_fields(self):
        for field_name in ("name", "country", "role", "comment"):
            self.fields[field_name].required = False

    def configure_country_field(self):
        country_widget = forms.TextInput(attrs=COUNTRY_COMBOBOX_WIDGET_ATTRS)
        self.fields["country"].widget = country_widget

    def configure_role_choices(self):
        role_choices = list(CourseRegistration.Role.choices)
        self.fields["role"].choices = [("", "Select role")] + role_choices

    def has_authenticated_user(self):
        return self.user is not None and self.user.is_authenticated

    def configure_authenticated_email_field(self):
        self.fields["email"].initial = self.user.email
        self.fields["email"].disabled = True
        self.fields["email"].help_text = "Using your account email."

    def authenticated_user_initial_values(self):
        name = (
            self.user.certificate_name
            or self.user.get_full_name()
            or ""
        )
        return {
            "name": name,
            "country": self.user.country,
            "role": self.user.registration_role,
        }

    def configure_authenticated_user(self):
        if not self.has_authenticated_user():
            return

        self.configure_authenticated_email_field()
        if not self.is_bound:
            initial_values = self.authenticated_user_initial_values()
            self.initial.update(initial_values)

    def clean_email(self):
        if self.user is not None and self.user.is_authenticated:
            email = self.user.email
        else:
            email = self.cleaned_data["email"]

        raw_email = email or ""
        email_stripped = raw_email.strip()
        email_normalized = email_stripped.lower()
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
        if not can_update_registration_user_profile(self.user):
            return

        update_fields = update_user_profile_from_registration(
            self.user,
            registration,
        )
        if update_fields:
            self.user.save(update_fields=update_fields)
