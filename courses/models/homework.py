from enum import Enum

from django.db import models
from django.core.validators import URLValidator
from django.contrib.auth import get_user_model

from .course import Course, Enrollment

User = get_user_model()


class HomeworkState(Enum):
    CLOSED = "CL"
    OPEN = "OP"
    SCORED = "SC"


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

    state = models.CharField(
        max_length=2,
        choices=[(state.value, state.name) for state in HomeworkState],
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
        split = [s.strip() for s in split]  # remove /r if present
        return split

    def get_correct_answer(self):
        if (self.question_type == QuestionTypes.CHECKBOXES.value) or (
            self.question_type == QuestionTypes.MULTIPLE_CHOICE.value
        ):
            if not self.correct_answer:
                return set()

            indicies_raw = self.correct_answer.split(",")
            indicies = [int(index) - 1 for index in indicies_raw]
            possible_answers = self.get_possible_answers()
            result = {possible_answers[i] for i in indicies}
            return result

        return self.correct_answer or ""

    def get_correct_answer_indices(self):
        if not self.correct_answer:
            return set()

        indicies_raw = self.correct_answer.split(",")
        indicies = {int(index) for index in indicies_raw}
        return indicies

    def __str__(self):
        return f"{self.homework.course.title} / {self.homework.title} - {self.text}"


class Submission(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)

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

    def __str__(self):
        return f"{self.student}'s submission for {self.homework.title}"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)

    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Answer id={self.id} for {self.question}"
