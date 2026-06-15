from django import forms

from courses.models import RegistrationCampaign


class RegistrationCampaignForm(forms.ModelForm):
    class Meta:
        model = RegistrationCampaign
        fields = [
            "title",
            "slug",
            "edition_label",
            "current_course",
            "is_active",
            "hero_image_url",
            "video_url",
            "meta_description",
            "marketing_markdown",
            "mailchimp_tag_before_switch",
            "mailchimp_tag_after_switch",
            "mailchimp_tag_switch_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "edition_label": forms.TextInput(attrs={"class": "form-control"}),
            "current_course": forms.Select(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "hero_image_url": forms.URLInput(attrs={"class": "form-control"}),
            "video_url": forms.URLInput(attrs={"class": "form-control"}),
            "meta_description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "marketing_markdown": forms.Textarea(
                attrs={"class": "form-control", "rows": 14}
            ),
            "mailchimp_tag_before_switch": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "mailchimp_tag_after_switch": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "mailchimp_tag_switch_at": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
        }
        labels = {
            "slug": "URL slug",
            "current_course": "Current course edition",
            "hero_image_url": "Hero image URL",
            "video_url": "Video URL",
            "mailchimp_tag_before_switch": "Mailchimp tag",
            "mailchimp_tag_after_switch": "Mailchimp tag after switch",
            "mailchimp_tag_switch_at": "Switch tag at",
        }
        help_texts = {
            "slug": "Public URL: /register/<slug>/",
            "edition_label": "Shown above the page title, for example 2026 cohort.",
            "current_course": "The course edition promoted by this landing page.",
            "is_active": "Inactive campaigns do not render publicly.",
            "meta_description": "Optional text for previews and search snippets.",
            "marketing_markdown": "Main landing-page body. Markdown is supported.",
            "mailchimp_tag_before_switch": "Applied to new registrations until the switch time.",
            "mailchimp_tag_after_switch": "Applied after the switch time, if set.",
            "mailchimp_tag_switch_at": "Optional local date/time for switching tags.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["current_course"].empty_label = "No current course"
        self.fields["mailchimp_tag_switch_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            for field_name in self.errors:
                if field_name in self.fields:
                    attrs = self.fields[field_name].widget.attrs
                    class_name = attrs.get("class", "")
                    if "is-invalid" not in class_name:
                        attrs["class"] = f"{class_name} is-invalid".strip()
        return valid
