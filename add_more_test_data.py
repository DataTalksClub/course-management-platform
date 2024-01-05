
import os

import random
from datetime import datetime, timedelta

import django
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")
django.setup()

from django.contrib.auth import get_user_model # noqa: E402

# This will retrieve your 'CustomUser' model
from courses.models import (  # noqa: E402
    Course,
    Enrollment,
    Homework,
    Question,
    Submission,
    Answer,
    QuestionTypes,
    AnswerTypes,
)


User = get_user_model()

# Fetch the existing course object by slug
course = Course.objects.get(slug="fake-course")

# Function to create questions for a given homework
def create_questions_for_homework(homework: Homework, num_questions=3):
    for i in range(num_questions):
        Question.objects.create(
            homework=homework,
            text=f"Question text {i+1}",
            correct_answer="Example answer",  # Set the correct answer
            question_type=QuestionTypes.FREE_FORM,
            answer_type=AnswerTypes.EXACT_STRING,
            scores_for_correct_answer=1,
        )

# Function to create answers for a student
def create_answers_for_student(submission):
    for question in submission.homework.question_set.all():
        is_correct = random.choice([True, False])  # Randomly decide if the answer is correct
        student_answer = question.correct_answer if is_correct else "Incorrect answer"
        Answer.objects.create(
            submission=submission,
            question=question,
            student=submission.student,
            answer_text=student_answer,
            is_correct=is_correct  # Assuming Answer model has an is_correct field
        )

# Create 5 homeworks with questions
for hw in range(1, 6):
    print(f"Creating homework {hw}")
    homework = Homework.objects.create(
        course=course,
        slug=f"extra-homework-{hw}",
        title=f"Test Homework {hw}",
        due_date=timezone.now() - timedelta(days=hw),
        description=f"Description for homework {hw}"
    )

    num_questions = random.randint(3, 5)
    create_questions_for_homework(homework, num_questions)


# Create 20 users and their submissions
for u in range(1, 21):
    username = f"student{u}"
    print(f"Creating student {username} and their submissions")

    user, created = User.objects.get_or_create(username=username)
    enrollment, created = Enrollment.objects.get_or_create(
        course=course,
        student=user,
    )

    # Each user makes a submission for each homework
    for homework in Homework.objects.filter(course=course):
        submission, created = Submission.objects.get_or_create(
            homework=homework,
            student=user,
            defaults={'enrollment': enrollment},
        )
        create_answers_for_student(submission)
