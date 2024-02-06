import random
from enum import Enum

from django.db import models

from django.core.validators import URLValidator

from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db.models import Sum

from .random_names import generate_random_name


User = get_user_model()


class Course(models.Model):
    slug = models.SlugField(unique=True, blank=False)
    title = models.CharField(max_length=200)

    description = models.TextField()
    students = models.ManyToManyField(
        User, through="Enrollment", related_name="courses_enrolled"
    )

    social_media_hashtag = models.CharField(
        max_length=100,
        blank=True,
        help_text="The hashtag associated with the course for social media use.",
    )

    # New field for the URL of the FAQ document
    faq_document_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
        help_text="The URL of the FAQ document for the course.",
    )

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    class Meta:
        unique_together = ["student", "course"]

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrollment_date = models.DateTimeField(auto_now_add=True)

    display_name = models.CharField(max_length=255, blank=True)
    display_on_leaderboard = models.BooleanField(default=True)

    certificate_name = models.CharField(
        max_length=255, blank=True, null=True
    )

    total_score = models.IntegerField(default=0)

    def calculate_total_score(self):
        submissions = Submission.objects.filter(enrollment=self)
        total_score_sum = submissions.aggregate(Sum("total_score"))[
            "total_score__sum"
        ]
        self.total_score = total_score_sum or 0
        self.save()

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = generate_random_name()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} enrolled in {self.course}"


class Homework(models.Model):
    slug = models.SlugField(blank=False)

    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    title = models.CharField(max_length=200)
    description = models.TextField()
    due_date = models.DateTimeField()

    learning_in_public_cap = models.IntegerField(default=7)

    homework_url_field = models.BooleanField(
        default=True, help_text="Include field for homework URL"
    )
    time_spent_lectures_field = models.BooleanField(
        default=True,
        help_text="Include field for time spent on lectures",
    )
    time_spent_homework_field = models.BooleanField(
        default=True,
        help_text="Include field for time spent on homework",
    )
    problems_comments_field = models.BooleanField(
        default=True,
        help_text="Include field for problems and comments",
    )
    faq_contribution_field = models.BooleanField(
        default=True, help_text="Include field for FAQ contributions"
    )

    is_scored = models.BooleanField(default=False)

    class Meta:
        unique_together = ("course", "slug")

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class QuestionTypes(Enum):
    MULTIPLE_CHOICE = "MC"
    FREE_FORM = "FF"
    CHECKBOXES = "CB"


class AnswerTypes(Enum):
    ANY = "ANY"
    FLOAT = "FLT"
    INTEGER = "INT"
    EXACT_STRING = "EXS"
    CONTAINS_STRING = "CTS"


QUESTION_ANSWER_DELIMITER = "\n"


class Question(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    text = models.TextField()

    QUESTION_TYPES = (
        (QuestionTypes.MULTIPLE_CHOICE.value, "Multiple Choice"),
        (QuestionTypes.FREE_FORM.value, "Free Form"),
        (QuestionTypes.CHECKBOXES.value, "Checkboxes"),
    )
    question_type = models.CharField(
        max_length=2, choices=QUESTION_TYPES
    )

    ANSWER_TYPES = (
        (AnswerTypes.ANY.value, "Any"),
        (AnswerTypes.FLOAT.value, "Float"),
        (AnswerTypes.INTEGER.value, "Integer"),
        (AnswerTypes.EXACT_STRING.value, "Exact String"),
        (AnswerTypes.CONTAINS_STRING.value, "Contains String"),
    )
    answer_type = models.CharField(
        max_length=3, choices=ANSWER_TYPES, blank=True, null=True
    )

    possible_answers = models.TextField(blank=True, null=True)
    correct_answer = models.TextField(blank=True, null=True)

    scores_for_correct_answer = models.IntegerField(default=1)

    def set_possible_answers(self, answers):
        self.possible_answers = QUESTION_ANSWER_DELIMITER.join(answers)

    def get_possible_answers(self):
        if not self.possible_answers:
            return []

        split = self.possible_answers.split(QUESTION_ANSWER_DELIMITER)
        return split

    def __str__(self):
        return f"{self.homework.course.title} / {self.homework.title} - {self.text}"


class Submission(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE
    )

    homework_link = models.URLField(
        blank=True,
        null=True,
        validators=[URLValidator(schemes=["http", "https", "git"])],
    )
    learning_in_public_links = models.JSONField(
        blank=True,
        null=True,
        help_text="Links where students talk about the course",
    )
    time_spent_lectures = models.FloatField(
        null=True,
        blank=True,
        help_text="Time spent on lectures and reading (in hours)",
    )
    time_spent_homework = models.FloatField(
        null=True,
        blank=True,
        help_text="Time spent on homework (in hours)",
    )
    problems_comments = models.TextField(
        blank=True, help_text="Any problems, comments, or feedback"
    )
    faq_contribution = models.TextField(
        blank=True, help_text="Contribution to FAQ"
    )

    submitted_at = models.DateTimeField(auto_now=True)

    questions_score = models.IntegerField(default=0)
    faq_score = models.IntegerField(default=0)
    learning_in_public_score = models.IntegerField(default=0)
    total_score = models.IntegerField(default=0)

    @property
    def answers_with_questions(self):
        questions = self.answer_set.select_related("question").all()
        return [(answer, answer.question) for answer in questions]

    def __str__(self):
        return (
            f"{self.student}'s submission for {self.homework.title}"
        )


class Answer(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)

    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Answer by {self.student} for {self.question}"


class ProjectState(Enum):
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
    time_spent_evaluation_field = models.BooleanField(default=True)

    points_to_pass = models.IntegerField(default=0)

    state = models.CharField(
        max_length=2,
        choices=[(state.value, state.name) for state in ProjectState],
        default=ProjectState.COLLECTING_SUBMISSIONS.value,
    )

    def __str__(self):
        return self.title

    class Meta:
        unique_together = ("course", "slug")


class ProjectSubmission(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE
    )

    github_link = models.URLField(validators=[URLValidator()])
    commit_id = models.CharField(max_length=40)

    learning_in_public_links = models.JSONField(blank=True, null=True)
    faq_contribution = models.TextField(blank=True)

    time_spent = models.FloatField()
    problems_comments = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.name} - {self.student.username}"


class ReviewCriteriaTypes(Enum):
    RADIO_BUTTONS = "RB"
    CHECKBOXES = "CB"


class ReviewCriteria(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    description = models.CharField(max_length=255)

    options = models.JSONField()

    max_score = models.IntegerField(default=4)

    REVIEW_CRITERIA_TYPES = (
        (ReviewCriteriaTypes.RADIO_BUTTONS.value, "Radio Buttons"),
        (ReviewCriteriaTypes.CHECKBOXES.value, "Checkboxes"),
    )

    review_criteria_type = models.CharField(
        max_length=2, choices=REVIEW_CRITERIA_TYPES
    )

    def __str__(self):
        return self.description


class PeerReview(models.Model):
    submission_under_evaluation = models.ForeignKey(
        ProjectSubmission, on_delete=models.CASCADE
    )
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    note_to_peer = models.TextField()
    learning_in_public_links = models.JSONField(blank=True, null=True)
    time_spent_reviewing = models.FloatField()
    comments = models.TextField(blank=True)

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
    score = models.IntegerField()

    def __str__(self):
        return f"{self.criteria.description}: {self.score}"
