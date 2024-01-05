
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


def create_random_question(homework: Homework):
    question_type = random.choice([QuestionTypes.FREE_FORM, QuestionTypes.MULTIPLE_CHOICE])
    print(f"Creating question of type {question_type} for homework {homework}")
    question_id = random.randint(1, 1000)

    if question_type == QuestionTypes.MULTIPLE_CHOICE:
        answers = "1,2,3,4"
        correct_answer = random.choice(answers.split(","))
        print(f"  Correct answer is {correct_answer}, possible answers are {answers}")

        return Question.objects.create(
            homework=homework,
            text=f"Question text {question_id}",
            correct_answer=correct_answer,
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=answers,
            scores_for_correct_answer=1,
        )

    elif question_type == QuestionTypes.FREE_FORM:
        correct_answer = "Example answer"
        print(f"  Correct answer is {correct_answer}")

        return Question.objects.create(
            homework=homework,
            text=f"Question text {question_id}",
            correct_answer=correct_answer,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
            scores_for_correct_answer=1,
        )

# Function to create questions for a given homework
def create_questions_for_homework(homework: Homework):
    num_questions = random.randint(3, 6)

    for i in range(num_questions):
        create_random_question(homework)


def generate_answer(question: Question, submission: Submission) -> Answer:
    is_correct = random.choice([True, False])
    
    student_answer = ""

    if is_correct:
        student_answer = question.correct_answer
    else:    
        if question.question_type == QuestionTypes.MULTIPLE_CHOICE.value:
            student_answer = random.choice(question.get_possible_answers())
        elif question.question_type == QuestionTypes.FREE_FORM.value:
            student_answer = "Incorrect answer"

    print(f"  Answer is correct: {is_correct}, student answer: {student_answer}")

    return Answer.objects.create(
        submission=submission,
        question=question,
        student=submission.student,
        answer_text=student_answer,
    )


def create_answers_for_student(submission):
    for question in submission.homework.question_set.all():
        generate_answer(question, submission)
        


for hw in range(1, 6):
    print(f"Creating homework {hw}")
    homework = Homework.objects.create(
        course=course,
        slug=f"extra-homework-{hw}",
        title=f"Test Homework {hw}",
        due_date=timezone.now() - timedelta(days=hw),
        description=f"Description for homework {hw}"
    )

    create_questions_for_homework(homework)


# Create 20 users and their submissions
for u in range(1, 21):
    username = f"student{u}"
    print(f"Creating student {username} and their submissions")

    user, created = User.objects.get_or_create(username=username)
    enrollment, created = Enrollment.objects.get_or_create(
        course=course,
        student=user,
    )

    for homework in Homework.objects.filter(course=course):
        submission, created = Submission.objects.get_or_create(
            homework=homework,
            student=user,
            defaults={'enrollment': enrollment},
        )
        create_answers_for_student(submission)
