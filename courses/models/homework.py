from enum import Enum

from django.db import models
from django.core.validators import URLValidator
from django.contrib.auth import get_user_model
from django.utils import timezone

from .course import Course, Enrollment
from .stat_display import StatSection, build_stat_fields
from courses.validators.custom_url_validators import validate_url_200

User = get_user_model()


class HomeworkState(Enum):
    CLOSED = "CL"
    OPEN = "OP"
    SCORED = "SC"


def _build_homework_state_choices():
    choices = []
    states = HomeworkState
    for state in states:
        choice = (state.value, state.name)
        choices.append(choice)
    return choices


HOMEWORK_STATE_CHOICES = _build_homework_state_choices()


class Homework(models.Model):
    slug = models.SlugField(blank=False)

    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructions_url = models.URLField(
        blank=True,
        null=True,
        validators=[URLValidator(schemes=["http", "https"])],
        help_text="Optional link to the homework instructions.",
    )
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

    faq_contribution_field = models.BooleanField(
        default=True, help_text="Include field for FAQ contributions"
    )

    state = models.CharField(
        max_length=2,
        choices=HOMEWORK_STATE_CHOICES,
        default=HomeworkState.OPEN.value,
    )

    def is_scored(self):
        return self.state == HomeworkState.SCORED.value

    class Meta:
        unique_together = ("course", "slug")

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class QuestionTypes(Enum):
    MULTIPLE_CHOICE = "MC"
    FREE_FORM = "FF"
    FREE_FORM_LONG = "FL"
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
        (QuestionTypes.FREE_FORM_LONG.value, "Free Form Long"),
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

    def get_possible_answers(self):
        if not self.possible_answers:
            return []

        possible_answers = []
        raw_answers = self.possible_answers.split(QUESTION_ANSWER_DELIMITER)
        for raw_answer in raw_answers:
            possible_answer = raw_answer.strip()
            possible_answers.append(possible_answer)
        return possible_answers

    def has_choice_answers(self):
        return self.question_type in {
            QuestionTypes.CHECKBOXES.value,
            QuestionTypes.MULTIPLE_CHOICE.value,
        }

    def zero_based_correct_answer_indices(self):
        if not self.correct_answer:
            return []

        indices_raw = self.correct_answer.split(",")
        indices = []
        for index_raw in indices_raw:
            index = int(index_raw) - 1
            indices.append(index)
        return indices

    def get_choice_correct_answer(self):
        possible_answers = self.get_possible_answers()
        correct_answers = set()
        correct_answer_indices = self.zero_based_correct_answer_indices()
        for index in correct_answer_indices:
            correct_answer = possible_answers[index]
            correct_answers.add(correct_answer)
        return correct_answers

    def get_correct_answer(self):
        if self.has_choice_answers():
            return self.get_choice_correct_answer()

        if self.correct_answer:
            return self.correct_answer
        return ""

    def get_correct_answer_indices(self):
        if not self.correct_answer:
            return set()

        indices_raw = self.correct_answer.split(",")
        indices = set()
        for index_raw in indices_raw:
            index = int(index_raw)
            indices.add(index)
        return indices

    def __str__(self):
        return f"{self.homework.course.title} / {self.homework.title} - {self.text}"


class Submission(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)

    homework_link = models.URLField(
        blank=True,
        null=True,
        validators=[
            URLValidator(schemes=["http", "https", "git"]),
            validate_url_200,
        ],
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
    faq_contribution_url = models.URLField(
        blank=True,
        null=True,
        help_text="Pull request or issue URL for the FAQ contribution",
    )

    submitted_at = models.DateTimeField(default=timezone.now)

    questions_score = models.IntegerField(default=0)
    faq_score = models.IntegerField(default=0)
    learning_in_public_score = models.IntegerField(default=0)
    total_score = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.student}'s submission for {self.homework.title}"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)

    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Answer id={self.id} for {self.question}"


class HomeworkStatistics(models.Model):
    homework = models.OneToOneField(
        Homework, on_delete=models.CASCADE, related_name="statistics"
    )

    total_submissions = models.IntegerField(default=0)

    # Fields for questions_score
    min_questions_score = models.IntegerField(null=True, blank=True)
    max_questions_score = models.IntegerField(null=True, blank=True)
    avg_questions_score = models.FloatField(null=True, blank=True)
    median_questions_score = models.FloatField(null=True, blank=True)
    q1_questions_score = models.FloatField(null=True, blank=True)
    q3_questions_score = models.FloatField(null=True, blank=True)

    # Fields for total_score
    min_total_score = models.IntegerField(null=True, blank=True)
    max_total_score = models.IntegerField(null=True, blank=True)
    avg_total_score = models.FloatField(null=True, blank=True)
    median_total_score = models.FloatField(null=True, blank=True)
    q1_total_score = models.FloatField(null=True, blank=True)
    q3_total_score = models.FloatField(null=True, blank=True)

    # Fields for learning_in_public_score
    min_learning_in_public_score = models.IntegerField(null=True, blank=True)
    max_learning_in_public_score = models.IntegerField(null=True, blank=True)
    avg_learning_in_public_score = models.FloatField(null=True, blank=True)
    median_learning_in_public_score = models.FloatField(null=True, blank=True)
    q1_learning_in_public_score = models.FloatField(null=True, blank=True)
    q3_learning_in_public_score = models.FloatField(null=True, blank=True)

    # Fields for time_spent_lectures
    min_time_spent_lectures = models.FloatField(null=True, blank=True)
    max_time_spent_lectures = models.FloatField(null=True, blank=True)
    avg_time_spent_lectures = models.FloatField(null=True, blank=True)
    median_time_spent_lectures = models.FloatField(null=True, blank=True)
    q1_time_spent_lectures = models.FloatField(null=True, blank=True)
    q3_time_spent_lectures = models.FloatField(null=True, blank=True)

    # Fields for time_spent_homework
    min_time_spent_homework = models.FloatField(null=True, blank=True)
    max_time_spent_homework = models.FloatField(null=True, blank=True)
    avg_time_spent_homework = models.FloatField(null=True, blank=True)
    median_time_spent_homework = models.FloatField(null=True, blank=True)
    q1_time_spent_homework = models.FloatField(null=True, blank=True)
    q3_time_spent_homework = models.FloatField(null=True, blank=True)

    last_calculated = models.DateTimeField(auto_now=True)

    def get_value(self, field_name, stats_type):
        attribute_name = f"{stats_type}_{field_name}"
        return getattr(self, attribute_name)

    def get_stat_fields(self):
        return build_stat_fields(self, [
            StatSection(
                "questions_score",
                "Questions score",
                "fas fa-question-circle",
            ),
            StatSection("total_score", "Total score", "fas fa-star"),
            StatSection(
                "time_spent_lectures",
                "Time spent on lectures",
                "fas fa-book-reader",
            ),
            StatSection(
                "time_spent_homework",
                "Time spent on homework",
                "fas fa-clock",
            ),
            StatSection(
                "learning_in_public_score",
                "Learning in public score",
                "fas fa-globe",
            ),
        ])

    def __str__(self):
        return f"Statistics for {self.homework.slug}"
