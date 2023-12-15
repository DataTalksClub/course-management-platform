from django.db import models
from django.contrib.auth import get_user_model

from courses.models import Course


User = get_user_model()


class Homework(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    due_date = models.DateTimeField()

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Question(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE)
    text = models.TextField()

    QUESTION_TYPES = (
        ('MC', 'Multiple Choice'),
        ('FF', 'Free Form'),
        ('CB', 'Checkboxes'),
    )
    question_type = models.CharField(max_length=2, choices=QUESTION_TYPES)

    ANSWER_TYPES = (
        ('ANY', 'Any'),
        ('FLT', 'Float'),
        ('INT', 'Integer'),
        ('EXS', 'Exact String'),
        ('CTS', 'Contains String'),
    )
    answer_type = models.CharField(max_length=3, choices=ANSWER_TYPES)

    possible_answers = models.TextField(blank=True, null=True)
    correct_answer = models.TextField(blank=True, null=True)

    def get_possible_answers(self):
        if not self.question.possible_answers:
            return []
        
        split = self.question.possible_answers.split(',')

        if self.answer_type == 'INT':
            split = [int(a) for a in split]
        elif self.answer_type == 'FLOAT':
            split = [float(a) for a in split]

        return split

    def __str__(self):
        return f"{self.homework.course.title} / {self.homework.title} - {self.text}"


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    answer_text = models.TextField()

    def __str__(self):
        return f"Answer by {self.student} for {self.question}"
