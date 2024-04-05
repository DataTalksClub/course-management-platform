from enum import Enum

from django.db import models
from django.core.validators import URLValidator
from django.contrib.auth import get_user_model

from .course import Course, Enrollment

User = get_user_model()


class ProjectState(Enum):
    COLLECTING_SUBMISSIONS = "CS"
    PEER_REVIEWING = "PR"
    COMPLETED = "CO"

project_state_names = {
    ProjectState.COLLECTING_SUBMISSIONS.value: "Collecting Submissions",
    ProjectState.PEER_REVIEWING.value: "Peer Reviewing",
    ProjectState.COMPLETED.value: "Completed",
}

project_status_badge_classes = {
    ProjectState.COLLECTING_SUBMISSIONS.value: "bg-info",
    ProjectState.PEER_REVIEWING.value: "bg-warning",
    ProjectState.COMPLETED.value: "bg-success",
}

class Project(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    slug = models.SlugField(blank=False)

    title = models.CharField(max_length=200)
    description = models.TextField()

    submission_due_date = models.DateTimeField()

    learning_in_public_cap_project = models.IntegerField(default=14)
    peer_review_due_date = models.DateTimeField()
    time_spent_project_field = models.BooleanField(default=True)

    problems_comments_field = models.BooleanField(default=True)
    faq_contribution_field = models.BooleanField(
        default=True, help_text="Include field for FAQ contributions"
    )

    learning_in_public_cap_review = models.IntegerField(default=2)
    number_of_peers_to_evaluate = models.IntegerField(default=3)
    time_spent_evaluation_field = models.BooleanField(default=True)

    points_to_pass = models.IntegerField(default=0)

    state = models.CharField(
        max_length=2,
        choices=[(state.value, state.name) for state in ProjectState],
        default=ProjectState.COLLECTING_SUBMISSIONS.value,
    )

    def get_project_state_name(self):
        return project_state_names[self.state]

    def status_badge_class(self):
        return project_status_badge_classes.get(self.state, "bg-secondary")

    def __str__(self):
        return self.title

    class Meta:
        unique_together = ("course", "slug")


class ProjectSubmission(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)

    github_link = models.URLField(validators=[URLValidator()])
    commit_id = models.CharField(max_length=40)

    learning_in_public_links = models.JSONField(blank=True, null=True)
    faq_contribution = models.TextField(blank=True)

    time_spent = models.FloatField(blank=True, null=True)
    problems_comments = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"project submission for enrollment {self.enrollment.id}"


class ReviewCriteriaTypes(Enum):
    RADIO_BUTTONS = "RB"
    CHECKBOXES = "CB"


class ReviewCriteria(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    description = models.CharField(max_length=255)

    options = models.JSONField()

    REVIEW_CRITERIA_TYPES = (
        (ReviewCriteriaTypes.RADIO_BUTTONS.value, "Radio Buttons"),
        (ReviewCriteriaTypes.CHECKBOXES.value, "Checkboxes"),
    )

    review_criteria_type = models.CharField(
        max_length=2, choices=REVIEW_CRITERIA_TYPES
    )

    def __str__(self):
        return self.description


class PeerReviewState(Enum):
    TO_REVIEW = "TR"
    SUBMITTED = "SU"


class PeerReview(models.Model):
    submission_under_evaluation = models.ForeignKey(
        ProjectSubmission,
        related_name="reviews_under_evaluation",
        on_delete=models.CASCADE,
    )
    reviewer = models.ForeignKey(
        ProjectSubmission,
        related_name="reviewers",
        on_delete=models.CASCADE,
    )
    note_to_peer = models.TextField()
    learning_in_public_links = models.JSONField(blank=True, null=True)
    time_spent_reviewing = models.FloatField(blank=True, null=True)
    problems_comments = models.TextField(blank=True)

    optional = models.BooleanField(
        default=False, null=False, blank=False
    )

    submitted_at = models.DateTimeField(null=True, blank=True)

    state = models.CharField(
        max_length=2,
        choices=[
            (state.value, state.name) for state in PeerReviewState
        ],
        default=PeerReviewState.TO_REVIEW.value,
    )

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.submission_under_evaluation.project.name}"

    def get_criteria_responses(self):
        return self.criteria_responses.all()


class CriteriaResponse(models.Model):
    review = models.ForeignKey(
        PeerReview,
        related_name="criteria_responses",
        on_delete=models.CASCADE,
    )
    criteria = models.ForeignKey(
        ReviewCriteria, on_delete=models.CASCADE
    )
    answer = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.criteria.description}: {self.answer}"

