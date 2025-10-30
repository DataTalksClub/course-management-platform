import math
import statistics
from enum import Enum

from django.db import models
from django.core.validators import URLValidator
from django.contrib.auth import get_user_model

from .course import Course, Enrollment
from courses.validators import validate_url_200

User = get_user_model()


class ProjectState(Enum):
    CLOSED = "CL"
    COLLECTING_SUBMISSIONS = "CS"
    PEER_REVIEWING = "PR"
    COMPLETED = "CO"


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
    points_for_peer_review = models.IntegerField(default=3)
    time_spent_evaluation_field = models.BooleanField(default=True)

    state = models.CharField(
        max_length=2,
        choices=[(state.value, state.name) for state in ProjectState],
        default=ProjectState.COLLECTING_SUBMISSIONS.value,
    )

    def __str__(self):
        return self.title

    @property
    def points_to_pass(self):
        """Get the passing score from the course"""
        return self.course.project_passing_score

    class Meta:
        unique_together = ("course", "slug")


class ProjectSubmission(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)

    github_link = models.URLField(
        validators=[URLValidator(), validate_url_200],
    )
    commit_id = models.CharField(max_length=40)

    learning_in_public_links = models.JSONField(blank=True, null=True)
    faq_contribution = models.TextField(blank=True)

    time_spent = models.FloatField(blank=True, null=True)
    problems_comments = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now=True)

    project_score = models.IntegerField(default=0)
    project_faq_score = models.IntegerField(default=0)
    project_learning_in_public_score = models.IntegerField(default=0)

    peer_review_score = models.IntegerField(default=0)
    peer_review_learning_in_public_score = models.IntegerField(
        default=0
    )

    total_score = models.IntegerField(default=0)

    reviewed_enough_peers = models.BooleanField(default=False)
    passed = models.BooleanField(default=False)

    def __str__(self):
        return f"project submission for enrollment {self.enrollment.id}"


class ReviewCriteriaTypes(Enum):
    RADIO_BUTTONS = "RB"
    CHECKBOXES = "CB"


class ReviewCriteria(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    description = models.CharField(max_length=255)

    options = models.JSONField()
    # example:
    # options=[
    #     {"criteria": "Poor", "score": 0},
    #     {"criteria": "Satisfactory", "score": 1},
    #     {"criteria": "Good", "score": 2},
    #     {"criteria": "Excellent", "score": 3},
    # ]

    REVIEW_CRITERIA_TYPES = (
        (ReviewCriteriaTypes.RADIO_BUTTONS.value, "Radio Buttons"),
        (ReviewCriteriaTypes.CHECKBOXES.value, "Checkboxes"),
    )

    review_criteria_type = models.CharField(
        max_length=2, choices=REVIEW_CRITERIA_TYPES
    )

    def median_score(self) -> int:
        result = 0
        scores = [option["score"] for option in self.options]

        if (
            self.review_criteria_type
            == ReviewCriteriaTypes.RADIO_BUTTONS.value
        ):
            result = statistics.median(scores)

        if (
            self.review_criteria_type
            == ReviewCriteriaTypes.CHECKBOXES.value
        ):
            result = sum(scores) / 2  # just give the middle score

        return math.ceil(result)

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
        return f"Peer review {self.id}, state={self.state}"

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

    def get_scores(self):
        criteria = self.criteria

        if not self.answer:
            return [0]

        answers = self.answer.split(",")
        answer_idx = [int(s) - 1 for s in answers]
        scores = [criteria.options[i]["score"] for i in answer_idx]

        return scores

    def get_score(self):
        return sum(self.get_scores())

    def __str__(self):
        return f"{self.criteria.description}: {self.answer}"


class ProjectEvaluationScore(models.Model):
    submission = models.ForeignKey(
        ProjectSubmission, on_delete=models.CASCADE
    )

    review_criteria = models.ForeignKey(
        ReviewCriteria, on_delete=models.CASCADE
    )

    score = models.IntegerField()

    def __str__(self):
        return f"Score: {self.score} for submission by {self.submission.id}"


class ProjectStatistics(models.Model):
    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="statistics"
    )

    total_submissions = models.IntegerField(default=0)

    # Fields for project_score
    min_project_score = models.IntegerField(null=True, blank=True)
    max_project_score = models.IntegerField(null=True, blank=True)
    avg_project_score = models.FloatField(null=True, blank=True)
    median_project_score = models.FloatField(null=True, blank=True)
    q1_project_score = models.FloatField(null=True, blank=True)
    q3_project_score = models.FloatField(null=True, blank=True)

    # Fields for project_learning_in_public_score
    min_project_learning_in_public_score = models.IntegerField(
        null=True, blank=True
    )
    max_project_learning_in_public_score = models.IntegerField(
        null=True, blank=True
    )
    avg_project_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    median_project_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    q1_project_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    q3_project_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )

    # Fields for peer_review_score
    min_peer_review_score = models.IntegerField(null=True, blank=True)
    max_peer_review_score = models.IntegerField(null=True, blank=True)
    avg_peer_review_score = models.FloatField(null=True, blank=True)
    median_peer_review_score = models.FloatField(null=True, blank=True)
    q1_peer_review_score = models.FloatField(null=True, blank=True)
    q3_peer_review_score = models.FloatField(null=True, blank=True)

    # Fields for peer_review_learning_in_public_score
    min_peer_review_learning_in_public_score = models.IntegerField(
        null=True, blank=True
    )
    max_peer_review_learning_in_public_score = models.IntegerField(
        null=True, blank=True
    )
    avg_peer_review_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    median_peer_review_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    q1_peer_review_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )
    q3_peer_review_learning_in_public_score = models.FloatField(
        null=True, blank=True
    )

    # Fields for total_score
    min_total_score = models.IntegerField(null=True, blank=True)
    max_total_score = models.IntegerField(null=True, blank=True)
    avg_total_score = models.FloatField(null=True, blank=True)
    median_total_score = models.FloatField(null=True, blank=True)
    q1_total_score = models.FloatField(null=True, blank=True)
    q3_total_score = models.FloatField(null=True, blank=True)

    # Fields for time_spent
    min_time_spent = models.FloatField(null=True, blank=True)
    max_time_spent = models.FloatField(null=True, blank=True)
    avg_time_spent = models.FloatField(null=True, blank=True)
    median_time_spent = models.FloatField(null=True, blank=True)
    q1_time_spent = models.FloatField(null=True, blank=True)
    q3_time_spent = models.FloatField(null=True, blank=True)

    last_calculated = models.DateTimeField(auto_now=True)

    def get_value(self, field_name, stats_type):
        attribute_name = f"{stats_type}_{field_name}"
        return getattr(self, attribute_name)

    def get_stat_fields(self):
        results = []

        results.append(
            (
                "Project score",
                [
                    (
                        self.min_project_score,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (
                        self.max_project_score,
                        "Maximum",
                        "fas fa-arrow-up",
                    ),
                    (
                        self.avg_project_score,
                        "Average",
                        "fas fa-equals",
                    ),
                    (
                        self.q1_project_score,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_project_score,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_project_score,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-project-diagram",
            )
        )

        results.append(
            (
                "Project learning in public score",
                [
                    (
                        self.min_project_learning_in_public_score,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (
                        self.max_project_learning_in_public_score,
                        "Maximum",
                        "fas fa-arrow-up",
                    ),
                    (
                        self.avg_project_learning_in_public_score,
                        "Average",
                        "fas fa-equals",
                    ),
                    (
                        self.q1_project_learning_in_public_score,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_project_learning_in_public_score,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_project_learning_in_public_score,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-globe",
            )
        )

        results.append(
            (
                "Peer review score",
                [
                    (
                        self.min_peer_review_score,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (
                        self.max_peer_review_score,
                        "Maximum",
                        "fas fa-arrow-up",
                    ),
                    (
                        self.avg_peer_review_score,
                        "Average",
                        "fas fa-equals",
                    ),
                    (
                        self.q1_peer_review_score,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_peer_review_score,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_peer_review_score,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-users",
            )
        )

        results.append(
            (
                "Peer review learning in public score",
                [
                    (
                        self.min_peer_review_learning_in_public_score,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (
                        self.max_peer_review_learning_in_public_score,
                        "Maximum",
                        "fas fa-arrow-up",
                    ),
                    (
                        self.avg_peer_review_learning_in_public_score,
                        "Average",
                        "fas fa-equals",
                    ),
                    (
                        self.q1_peer_review_learning_in_public_score,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_peer_review_learning_in_public_score,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_peer_review_learning_in_public_score,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-share-alt",
            )
        )

        results.append(
            (
                "Total score",
                [
                    (
                        self.min_total_score,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (
                        self.max_total_score,
                        "Maximum",
                        "fas fa-arrow-up",
                    ),
                    (self.avg_total_score, "Average", "fas fa-equals"),
                    (
                        self.q1_total_score,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_total_score,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_total_score,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-star",
            )
        )

        results.append(
            (
                "Time spent on project",
                [
                    (
                        self.min_time_spent,
                        "Minimum",
                        "fas fa-arrow-down",
                    ),
                    (self.max_time_spent, "Maximum", "fas fa-arrow-up"),
                    (self.avg_time_spent, "Average", "fas fa-equals"),
                    (
                        self.q1_time_spent,
                        "25th Percentile",
                        "fas fa-percentage",
                    ),
                    (
                        self.median_time_spent,
                        "Median",
                        "fas fa-percentage",
                    ),
                    (
                        self.q3_time_spent,
                        "75th Percentile",
                        "fas fa-percentage",
                    ),
                ],
                "fas fa-clock",
            )
        )

        return results

    def __str__(self):
        return f"Statistics for {self.project.slug}"
