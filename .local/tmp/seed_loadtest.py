"""Seed a large scorable homework for load testing.

Env: DATABASE_URL, SEED_SUBMISSIONS (default 400), SEED_QUESTIONS (default 10).
Prints KEY=VALUE lines: TOKEN, COURSE_SLUG, HOMEWORK_ID, HOMEWORK_SLUG.
Idempotent per database: slugs include SEED_TAG.
"""

import os
import sys
from datetime import timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import Token  # noqa: E402
from courses.models import (  # noqa: E402
    Answer,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    Submission,
)

User = get_user_model()

TAG = os.environ.get("SEED_TAG", "load")
N_SUB = int(os.environ.get("SEED_SUBMISSIONS", "400"))
N_Q = int(os.environ.get("SEED_QUESTIONS", "10"))

staff, _ = User.objects.get_or_create(
    username=f"loadstaff-{TAG}",
    defaults={"email": f"loadstaff-{TAG}@example.com", "is_staff": True},
)
staff.is_staff = True
staff.set_password("x")
staff.save()
token, _ = Token.objects.get_or_create(user=staff)

course, _ = Course.objects.get_or_create(
    slug=f"load-course-{TAG}",
    defaults={"title": f"Load {TAG}", "description": "load test"},
)
homework, _ = Homework.objects.get_or_create(
    course=course,
    slug=f"load-hw-{TAG}",
    defaults={
        "title": f"Load HW {TAG}",
        "due_date": timezone.now() - timedelta(hours=1),
        "state": HomeworkState.OPEN.value,
    },
)
homework.due_date = timezone.now() - timedelta(hours=1)
homework.state = HomeworkState.OPEN.value
homework.save()

questions = list(Question.objects.filter(homework=homework).order_by("id"))
while len(questions) < N_Q:
    questions.append(
        Question.objects.create(
            homework=homework,
            text=f"Q{len(questions)}: 2+2?",
            question_type="FF",
            answer_type="EXS",
            correct_answer="4",
            scores_for_correct_answer=1,
        )
    )

existing = Submission.objects.filter(homework=homework).count()
need = max(0, N_SUB - existing)
for i in range(need):
    idx = existing + i
    student, _ = User.objects.get_or_create(
        username=f"loadstu-{TAG}-{idx:04d}",
        defaults={"email": f"loadstu-{TAG}-{idx:04d}@example.com"},
    )
    enrollment = Enrollment.objects.create(student=student, course=course)
    sub = Submission.objects.create(
        homework=homework, student=student, enrollment=enrollment
    )
    Answer.objects.bulk_create(
        [
            Answer(submission=sub, question=q, answer_text="4")
            for q in questions
        ]
    )

print(f"TOKEN={token.key}")
print(f"COURSE_SLUG={course.slug}")
print(f"HOMEWORK_ID={homework.id}")
print(f"HOMEWORK_SLUG={homework.slug}")
print(f"SUBMISSIONS={Submission.objects.filter(homework=homework).count()}")
print(f"QUESTIONS={len(questions)}")
