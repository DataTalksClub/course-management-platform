from django import forms

from courses.email_validation import (
    email_domain_has_mx,
    suggest_email_correction,
)
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
YEARS_EXPERIENCE_WIDGET = forms.Select(attrs={"class": "form-control"})
COMMENT_WIDGET = forms.Textarea(
    attrs={
        "class": "form-control",
        "rows": 4,
        "placeholder": "Anything you would like to add?",
    }
)
EXPERIENCE_WIDGET = forms.Textarea(
    attrs={
        "class": "form-control",
        "rows": 4,
        "placeholder": "Your role and experience, e.g. years, stack, ML/production background",
    }
)
WHY_JOIN_WIDGET = forms.Textarea(
    attrs={
        "class": "form-control",
        "rows": 4,
        "placeholder": "Why do you want to join this course?",
    }
)
URL_WIDGET = forms.URLInput(attrs={"class": "form-control"})
PREREQ_WIDGET = forms.CheckboxInput(attrs={"class": "h-4 w-4"})
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

    country_widget = forms.TextInput(
        attrs=COUNTRY_COMBOBOX_WIDGET_ATTRS
    )
    form.fields["country"].widget = country_widget

    role_choices = [("", "Select role")]
    for role_choice in CourseRegistration.Role.choices:
        role_choices.append(role_choice)
    form.fields["role"].choices = role_choices

    years_choices = [("", "Select years of experience")]
    for years_choice in CourseRegistration.YearsExperience.choices:
        years_choices.append(years_choice)
    if "years_experience" in form.fields:
        form.fields["years_experience"].choices = years_choices


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
    experience = forms.CharField(
        label="Role and experience",
        required=False,
        widget=EXPERIENCE_WIDGET,
        help_text="Tell us about your role and relevant experience.",
    )
    why_join = forms.CharField(
        label="Why do you want to join?",
        required=False,
        widget=WHY_JOIN_WIDGET,
    )
    years_experience = forms.ChoiceField(
        label="Years of professional software or ML experience",
        required=False,
        widget=YEARS_EXPERIENCE_WIDGET,
        choices=[],
        help_text="Optional.",
    )
    linkedin_url = forms.URLField(
        label="LinkedIn profile",
        required=False,
        widget=URL_WIDGET,
        assume_scheme="https",
    )
    github_url = forms.URLField(
        label="GitHub profile",
        required=False,
        widget=URL_WIDGET,
        assume_scheme="https",
    )
    prereq_python = forms.BooleanField(
        label="I am comfortable with Python",
        required=False,
        widget=PREREQ_WIDGET,
    )
    prereq_docker = forms.BooleanField(
        label="I know Docker basics",
        required=False,
        widget=PREREQ_WIDGET,
    )
    prereq_http = forms.BooleanField(
        label="I have worked with HTTP APIs",
        required=False,
        widget=PREREQ_WIDGET,
    )
    prereq_cli = forms.BooleanField(
        label="I am comfortable with the command line",
        required=False,
        widget=PREREQ_WIDGET,
    )
    accepted_nebius_sharing = forms.BooleanField(
        label=(
            "Share my application with Nebius and Nebius Academy "
            "for review, credits and course operation"
        ),
        required=False,
        widget=ACCEPTED_NEWSLETTER_WIDGET,
        help_text="Required for application-review courses.",
    )

    class Meta:
        model = CourseRegistration
        fields = [
            "email",
            "name",
            "company_name",
            "country",
            "role",
            "experience",
            "years_experience",
            "why_join",
            "linkedin_url",
            "github_url",
            "prereq_python",
            "prereq_docker",
            "prereq_http",
            "prereq_cli",
            "comment",
            "accepted_newsletter",
            "accepted_nebius_sharing",
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
        self.apply_registration_wall_requirements()

    def campaign_has_registration_wall(self):
        campaign = self.campaign
        if campaign is None:
            return False
        course = getattr(campaign, "current_course", None)
        if course is None:
            return False
        return bool(
            getattr(course, "requires_registration_approval", False)
        )

    def apply_registration_wall_requirements(self):
        if not self.campaign_has_registration_wall():
            # Nebius sharing consent only applies to application-review
            # (wall) courses; keep other campaigns' forms unchanged.
            self.fields.pop("accepted_nebius_sharing", None)
            return
        for field_name in (
            "name",
            "role",
            "experience",
            "accepted_nebius_sharing",
        ):
            self.fields[field_name].required = True

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
        suggestion = suggest_email_correction(email_normalized)
        if suggestion and suggestion.lower() != email_normalized:
            raise forms.ValidationError(f"Did you mean {suggestion}?")
        mx_result = email_domain_has_mx(email_normalized)
        if mx_result is False:
            raise forms.ValidationError(
                "That email domain does not accept mail. "
                "Please check the address."
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

    def clean_accepted_nebius_sharing(self):
        accepted_nebius_sharing = self.cleaned_data.get(
            "accepted_nebius_sharing"
        )
        if (
            "accepted_nebius_sharing" in self.fields
            and self.fields["accepted_nebius_sharing"].required
            and not accepted_nebius_sharing
        ):
            raise forms.ValidationError("This field is required.")
        return bool(accepted_nebius_sharing)

    def save(self, commit=True):
        registration = super().save(commit=False)
        registration.campaign = self.campaign
        registration.course = self.campaign.current_course
        registration.region = region_for_country(registration.country)
        if has_authenticated_registration_user(self.user):
            registration.user = self.user
            registration.email = self.user.email
        else:
            # clean_email() normalizes; keep the exact address the user
            # typed so the pending page can show it back verbatim.
            raw_email = ""
            if hasattr(self, "data") and self.data is not None:
                raw_email = self.data.get("email", "")
            raw_email = (raw_email or "").strip()
            if raw_email:
                registration.email = raw_email
        if commit:
            registration.save()
            save_registration_user_profile(self.user, registration)
        return registration
