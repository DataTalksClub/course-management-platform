from django import forms

from courses.models.course import CourseRegistration
from courses.registration import region_for_country
from courses.views.registration_profile import (
    update_user_profile_from_registration,
)


ACCEPTED_NEWSLETTER_WIDGET = forms.CheckboxInput(
    attrs={"class": "h-4 w-4"}
)
EMAIL_WIDGET = forms.EmailInput(attrs={"class": "form-control"})
NAME_WIDGET = forms.TextInput(attrs={"class": "form-control"})
COMPANY_NAME_WIDGET = forms.TextInput(
    attrs={"class": "form-control", "autocomplete": "organization"}
)
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
OPTIONAL_REGISTRATION_FIELDS = (
    "name",
    "company_name",
    "country",
    "role",
    "comment",
)


def configure_registration_form_fields(form):
    for field_name in OPTIONAL_REGISTRATION_FIELDS:
        form.fields[field_name].required = False

    country_widget = forms.TextInput(attrs=COUNTRY_COMBOBOX_WIDGET_ATTRS)
    form.fields["country"].widget = country_widget

    role_choices = [("", "Select role")]
    for role_choice in CourseRegistration.Role.choices:
        role_choices.append(role_choice)
    form.fields["role"].choices = role_choices


def has_authenticated_registration_user(user):
    return user is not None and user.is_authenticated


def authenticated_registration_initial_values(user):
    name = user.certificate_name or user.get_full_name() or ""
    return {
        "name": name,
        "country": user.country,
        "role": user.registration_role,
    }


def configure_authenticated_registration_user(form, user):
    if not has_authenticated_registration_user(user):
        return

    form.fields["email"].initial = user.email
    form.fields["email"].disabled = True
    form.fields["email"].help_text = "Using your account email."

    if not form.is_bound:
        initial_values = authenticated_registration_initial_values(user)
        form.initial.update(initial_values)


def normalized_registration_email(email):
    raw_email = email or ""
    email_stripped = raw_email.strip()
    return email_stripped.lower()


def registration_email_taken(campaign, email_normalized):
    return CourseRegistration.objects.filter(
        campaign=campaign,
        email_normalized=email_normalized,
    ).exists()


def save_registration_user_profile(user, registration):
    if not has_authenticated_registration_user(user):
        return

    update_fields = update_user_profile_from_registration(
        user,
        registration,
    )
    if update_fields:
        user.save(update_fields=update_fields)


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
            "company_name",
            "country",
            "role",
            "comment",
            "accepted_newsletter",
        ]
        widgets = {
            "email": EMAIL_WIDGET,
            "name": NAME_WIDGET,
            "company_name": COMPANY_NAME_WIDGET,
            "country": COUNTRY_SELECT_WIDGET,
            "role": ROLE_WIDGET,
            "comment": COMMENT_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        configure_registration_form_fields(self)
        configure_authenticated_registration_user(self, self.user)

    def clean_email(self):
        if has_authenticated_registration_user(self.user):
            email = self.user.email
        else:
            email = self.cleaned_data["email"]

        email_normalized = normalized_registration_email(email)
        if registration_email_taken(self.campaign, email_normalized):
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
        if has_authenticated_registration_user(self.user):
            registration.user = self.user
            registration.email = self.user.email
        if commit:
            registration.save()
            save_registration_user_profile(self.user, registration)
        return registration
