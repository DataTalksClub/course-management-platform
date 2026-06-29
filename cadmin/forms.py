from django import forms

from courses.models import RegistrationCampaign


class HomeworkSubmissionEditForm(forms.Form):
    learning_in_public_links = forms.CharField(required=False)
    faq_contribution_url = forms.CharField(required=False)
    faq_score = forms.IntegerField(required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        submission = kwargs.pop("submission")
        questions = kwargs.pop("questions")
        super().__init__(*args, **kwargs)
        self.submission = submission
        self.questions = list(questions)

        form_questions = self.questions
        for question in form_questions:
            self.fields[f"answer_{question.id}"] = forms.CharField(
                required=False
            )

    def clean_faq_score(self):
        score = self.cleaned_data["faq_score"]
        if score is None:
            return self.submission.faq_score
        return score

    def clean(self):
        cleaned_data = super().clean()
        answers_by_question = []
        questions = self.questions
        for question in questions:
            answer = (
                question,
                cleaned_data.get(f"answer_{question.id}", ""),
            )
            answers_by_question.append(answer)
        cleaned_data["answers_by_question"] = answers_by_question

        links_text = cleaned_data.get("learning_in_public_links", "")
        links = []
        raw_links = links_text.splitlines()
        for raw_link in raw_links:
            link = raw_link.strip()
            if link:
                links.append(link)
        cleaned_data["learning_in_public_links_list"] = links or None
        return cleaned_data


class ProjectSubmissionEditForm(forms.Form):
    project_faq_score = forms.IntegerField()
    project_learning_in_public_score = forms.IntegerField()
    peer_review_score = forms.IntegerField()
    peer_review_learning_in_public_score = forms.IntegerField()
    reviewed_enough_peers = forms.BooleanField(required=False)
    passed = forms.BooleanField(required=False)

    def __init__(self, *args, review_criteria, **kwargs):
        super().__init__(*args, **kwargs)
        self.review_criteria = list(review_criteria)

        review_criteria_items = self.review_criteria
        for criteria in review_criteria_items:
            self.fields[f"criteria_score_{criteria.id}"] = (
                forms.IntegerField(
                    min_value=0,
                    label=criteria.description,
                )
            )

    def clean(self):
        cleaned_data = super().clean()
        criteria_scores = []
        review_criteria_items = self.review_criteria
        for criteria in review_criteria_items:
            criteria_score = (
                criteria,
                cleaned_data.get(f"criteria_score_{criteria.id}", 0),
            )
            criteria_scores.append(criteria_score)
        cleaned_data["criteria_scores"] = criteria_scores
        return cleaned_data


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
        }
        labels = {
            "slug": "URL slug",
            "current_course": "Current course edition",
            "hero_image_url": "Hero image URL",
            "video_url": "Video URL",
        }
        help_texts = {
            "slug": "Public URL: /register/<slug>/",
            "edition_label": "Shown above the page title, for example 2026 cohort.",
            "current_course": "The course edition promoted by this landing page.",
            "is_active": "Inactive campaigns do not render publicly.",
            "meta_description": "Optional text for previews and search snippets.",
            "marketing_markdown": "Main landing-page body. Markdown is supported.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["current_course"].empty_label = "No current course"

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            error_field_names = self.errors
            for field_name in error_field_names:
                if field_name in self.fields:
                    attrs = self.fields[field_name].widget.attrs
                    class_name = attrs.get("class", "")
                    if "is-invalid" not in class_name:
                        attrs["class"] = f"{class_name} is-invalid".strip()
        return valid
