import random
from enum import Enum

from django.db import models

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

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    class Meta:
        unique_together = ["student", "course"]

    student = models.ForeignKey(User, on_delete=models.PROTECT)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrollment_date = models.DateTimeField(auto_now_add=True)

    display_name = models.CharField(max_length=255, blank=True, default="Anonymous")
    total_score = models.IntegerField(default=0)

    def calculate_total_score(self):
        submissions = Submission.objects.filter(enrollment=self)
        total_score_sum = submissions.aggregate(Sum("total_score"))["total_score__sum"]
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


class Question(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    text = models.TextField()

    QUESTION_TYPES = (
        (QuestionTypes.MULTIPLE_CHOICE.value, "Multiple Choice"),
        (QuestionTypes.FREE_FORM.value, "Free Form"),
        (QuestionTypes.CHECKBOXES.value, "Checkboxes"),
    )
    question_type = models.CharField(max_length=2, choices=QUESTION_TYPES)

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

        split = self.possible_answers.split(",")
        return split

    def __str__(self):
        return f"{self.homework.course.title} / {self.homework.title} - {self.text}"


class Submission(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)

    submitted_at = models.DateTimeField(auto_now=True)
    total_score = models.IntegerField(default=0)

    @property
    def answers_with_questions(self):
        questions = self.answer_set.select_related("question").all()
        return [(answer, answer.question) for answer in questions]

    def __str__(self):
        return f"{self.student}'s submission for {self.homework.title}"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    answer_text = models.TextField()

    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Answer by {self.student} for {self.question}"
