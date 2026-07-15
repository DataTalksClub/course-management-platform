from django import forms

from courses.models.course import RegistrationCampaign
from courses.models.homework import Question


REGISTRATION_CAMPAIGN_TITLE_WIDGET = forms.TextInput(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_SLUG_WIDGET = forms.TextInput(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_EDITION_WIDGET = forms.TextInput(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_COURSE_WIDGET = forms.Select(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_ACTIVE_WIDGET = forms.CheckboxInput(
    attrs={"class": "form-check-input"}
)
REGISTRATION_CAMPAIGN_HERO_URL_WIDGET = forms.URLInput(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_VIDEO_URL_WIDGET = forms.URLInput(
    attrs={"class": "form-control"}
)
REGISTRATION_CAMPAIGN_META_DESCRIPTION_WIDGET = forms.Textarea(
    attrs={"class": "form-control", "rows": 3}
)
REGISTRATION_CAMPAIGN_MARKETING_WIDGET = forms.Textarea(
    attrs={"class": "form-control", "rows": 14}
)


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

        for question in self.questions:
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
        for question in self.questions:
            answer_text = cleaned_data.get(f"answer_{question.id}", "")
            answer = (
                question,
                answer_text,
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

        for criteria in self.review_criteria:
            self.fields[f"criteria_score_{criteria.id}"] = (
                forms.IntegerField(
                    min_value=0,
                    label=criteria.description,
                )
            )

    def clean(self):
        cleaned_data = super().clean()
        criteria_scores = []
        for criteria in self.review_criteria:
            score = cleaned_data.get(f"criteria_score_{criteria.id}", 0)
            criteria_score = (
                criteria,
                score,
            )
            criteria_scores.append(criteria_score)
        cleaned_data["criteria_scores"] = criteria_scores
        return cleaned_data


class HomeworkAnswersForm(forms.Form):
    """Edit correct answers and answer types per question.

    For choice questions (MC/CB) the correct_answer field holds
    1-based option indices. For free-form questions it holds the
    expected text value.
    """

    def __init__(self, *args, **kwargs):
        questions = kwargs.pop("questions")
        super().__init__(*args, **kwargs)
        self.questions = list(questions)

        for question in self.questions:
            self.fields[f"correct_answer_{question.id}"] = forms.CharField(
                required=False,
                initial=question.correct_answer or "",
                widget=forms.TextInput(
                    attrs={"class": "form-control"}
                ),
            )
            self.fields[f"answer_type_{question.id}"] = forms.ChoiceField(
                required=False,
                choices=[("", "---")] + list(Question.ANSWER_TYPES),
                initial=question.answer_type or "",
                widget=forms.Select(
                    attrs={"class": "form-control"}
                ),
            )

    def question_fields(self, question):
        """Return (correct_answer_field, answer_type_field) bound fields."""
        return (
            self[f"correct_answer_{question.id}"],
            self[f"answer_type_{question.id}"],
        )

    def save(self):
        for question in self.questions:
            correct_answer = self.cleaned_data.get(
                f"correct_answer_{question.id}", ""
            )
            answer_type = self.cleaned_data.get(
                f"answer_type_{question.id}", ""
            )
            question.correct_answer = correct_answer
            question.answer_type = answer_type or None
            question.save(update_fields=["correct_answer", "answer_type"])


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
            "title": REGISTRATION_CAMPAIGN_TITLE_WIDGET,
            "slug": REGISTRATION_CAMPAIGN_SLUG_WIDGET,
            "edition_label": REGISTRATION_CAMPAIGN_EDITION_WIDGET,
            "current_course": REGISTRATION_CAMPAIGN_COURSE_WIDGET,
            "is_active": REGISTRATION_CAMPAIGN_ACTIVE_WIDGET,
            "hero_image_url": REGISTRATION_CAMPAIGN_HERO_URL_WIDGET,
            "video_url": REGISTRATION_CAMPAIGN_VIDEO_URL_WIDGET,
            "meta_description": REGISTRATION_CAMPAIGN_META_DESCRIPTION_WIDGET,
            "marketing_markdown": REGISTRATION_CAMPAIGN_MARKETING_WIDGET,
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
