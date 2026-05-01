#!/usr/bin/env python
# ruff: noqa: E402
"""Generate production-like course data for leaderboard and YAML testing.

Run from the repository root:

    uv run python scripts/generate_production_like_leaderboard_data.py
    uv run python scripts/generate_production_like_leaderboard_data.py --list-courses
    uv run python scripts/generate_production_like_leaderboard_data.py --catalog-only
    uv run python scripts/generate_production_like_leaderboard_data.py --course de-zoomcamp-2026 --count 1000

The course/homework/project structure is based on courses.datatalks.club as
observed on 2026-05-01.
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django

django.setup()

from django.core.cache import cache
from django.db import OperationalError, connection
from django.utils.text import slugify

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    AnswerTypes,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
    User,
)
from courses.scoring import (
    calculate_homework_statistics,
    calculate_project_statistics,
    update_leaderboard,
)


USER_PREFIX = "production-like-user"

DEFAULT_SELECTED_COURSES = {
    "de-zoomcamp-2026": 1200,
    "ml-zoomcamp-2025": 1000,
    "llm-zoomcamp-2025": 800,
    "mlops-zoomcamp-2025": 650,
    "sma-zoomcamp-2025": 450,
}


def configure_sqlite_busy_timeout():
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout = 10000")


def run_with_lock_retries(action, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == attempts:
                raise
            time.sleep(attempt)

COURSE_SPECS = [
    {
        "slug": "de-zoomcamp-2026",
        "title": "Data Engineering Zoomcamp 2026",
        "finished": False,
        "homeworks": [
            ("Homework 1: Docker, SQL and Terraform", "2026-01-26T23:59:59+00:00"),
            ("Homework 2: Workflow Orchestration", "2026-02-02T23:59:59+00:00"),
            ("Homework 3: Data Warehousing", "2026-02-09T23:59:59+00:00"),
            ("Homework 4: Analytics Engineering", "2026-02-16T23:59:59+00:00"),
            ("Homework 5: Data Platforms", "2026-02-28T23:59:59+00:00"),
            ("Workshop 1: Ingestion with dlt", "2026-03-02T23:59:59+00:00"),
            ("Homework 6: Batch", "2026-03-09T23:59:59+00:00"),
            ("Homework 7: Streaming", "2026-03-19T23:59:59+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2026-04-08T23:59:59+00:00"),
            ("Project Attempt 2", "2026-04-27T23:59:59+00:00"),
            ("Last Project Attempt", "2026-05-04T23:00:00+00:00"),
        ],
    },
    {
        "slug": "ai-dev-tools-2025",
        "title": "AI Dev Tools Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction", "2025-11-27T23:00:00+00:00"),
            ("Homework 2: End-To-End Project", "2025-12-08T23:00:00+00:00"),
            ("Homework 3: MCP", "2026-01-05T23:00:00+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2026-01-28T23:00:00+00:00"),
            ("Project Attempt 2", "2026-02-02T23:00:00+00:00"),
        ],
    },
    {
        "slug": "ml-zoomcamp-2025",
        "title": "Machine Learning Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction to Machine Learning", "2025-10-01T23:00:00+00:00"),
            ("Homework 2: Machine Learning for Regression", "2025-10-08T23:00:00+00:00"),
            ("Homework 3: Machine Learning for Classification", "2025-10-15T23:00:00+00:00"),
            ("Homework 4: Evaluation Metrics for Classification", "2025-10-20T23:00:00+00:00"),
            ("Homework 5: Deploying Machine Learning Models", "2025-10-30T23:00:00+00:00"),
            ("Homework 6: Decision Trees and Ensemble Learning", "2025-11-08T23:00:00+00:00"),
            ("Homework 8: Neural Networks and Deep Learning", "2025-12-01T23:00:00+00:00"),
            ("Homework 9: Serverless Deep Learning", "2025-12-08T23:00:00+00:00"),
            ("Homework 10: Kubernetes", "2025-12-15T23:00:00+00:00"),
        ],
        "projects": [
            ("Midterm Project", "2025-11-27T23:00:00+00:00"),
            ("Capstone 1", "2026-01-12T23:00:00+00:00"),
            ("Capstone 2", "2026-01-26T23:00:00+00:00"),
            ("Capstone 3", "2026-02-09T23:00:00+00:00"),
        ],
    },
    {
        "slug": "llm-zoomcamp-2025",
        "title": "LLM Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction", "2025-06-16T23:00:00+00:00"),
            ("Homework 2: Vector Search", "2025-06-30T23:00:00+00:00"),
            ("dlt Workshop", "2025-07-10T23:00:00+00:00"),
            ("Agents", "2025-08-10T23:00:00+00:00"),
            ("Homework 3: Evaluation", "2025-08-11T23:00:00+00:00"),
        ],
        "projects": [
            ("Project 1", "2025-09-29T23:00:00+00:00"),
            ("Project 2", "2025-10-20T23:00:00+00:00"),
            ("Project 3", "2025-10-26T23:00:00+00:00"),
        ],
    },
    {
        "slug": "sma-zoomcamp-2025",
        "title": "Stock Markets Analytics Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Intro and Data Sources", "2025-06-04T22:59:59+00:00"),
            ("Homework 2: Working with Data in Pandas", "2025-06-23T22:59:59+00:00"),
            ("Homework 3: Modeling for Financial Time Series", "2025-07-14T23:59:59+00:00"),
            ("Homework 4: Trading Simulation", "2025-08-04T22:59:59+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2025-09-03T23:59:59+00:00"),
            ("Project Attempt 2", "2025-09-30T23:59:59+00:00"),
        ],
    },
    {
        "slug": "mlops-zoomcamp-2025",
        "title": "MLOps Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction", "2025-05-19T23:00:00+00:00"),
            ("Homework 2: Experiment Tracking", "2025-05-26T23:00:00+00:00"),
            ("Homework 3: Training Pipelines", "2025-06-09T23:00:00+00:00"),
            ("Homework 4: Deployment", "2025-06-16T23:00:00+00:00"),
            ("Homework 5: Monitoring", "2025-06-23T23:00:00+00:00"),
            ("Homework 6: Best Practices", "2025-06-30T23:00:00+00:00"),
        ],
        "projects": [
            ("Attempt 1", "2025-07-23T23:00:00+00:00"),
            ("Attempt 2", "2025-08-11T23:00:00+00:00"),
            ("Attempt 3", "2025-08-29T17:00:00+00:00"),
        ],
    },
    {
        "slug": "de-zoomcamp-2025",
        "title": "Data Engineering Zoomcamp 2025",
        "finished": True,
        "homeworks": [
            ("Homework 1: Docker, SQL and Terraform", "2025-01-27T23:00:00+00:00"),
            ("Homework 2: Workflow Orchestration", "2025-02-05T23:00:00+00:00"),
            ("Homework 3: Data Warehousing", "2025-02-12T23:00:00+00:00"),
            ("Workshop 1: Ingestion with dlt", "2025-02-16T23:00:00+00:00"),
            ("Homework 4: Analytics Engineering", "2025-02-26T23:00:00+00:00"),
            ("Homework 5: Batch", "2025-03-06T23:00:00+00:00"),
            ("Homework 6: Streaming", "2025-03-17T23:00:00+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2025-04-07T23:00:00+00:00"),
            ("Project Attempt 2", "2025-04-28T23:00:00+00:00"),
            ("Project Attempt 3", "2025-05-05T23:00:00+00:00"),
        ],
    },
    {
        "slug": "ml-zoomcamp-2024",
        "title": "Machine Learning Zoomcamp 2024",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction to Machine Learning", "2024-09-30T23:00:00+00:00"),
            ("Homework 2: Machine Learning for Regression", "2024-10-09T23:00:00+00:00"),
            ("Homework 3: Machine Learning for Classification", "2024-10-16T23:00:00+00:00"),
            ("Homework 4: Evaluation Metrics for Classification", "2024-10-21T23:00:00+00:00"),
            ("Homework 5: Deploying Machine Learning Models", "2024-10-28T23:00:00+00:00"),
            ("Homework 6: Decision Trees and Ensemble Learning", "2024-11-04T23:00:00+00:00"),
            ("Homework 8: Neural Networks and Deep Learning", "2024-12-06T23:00:00+00:00"),
            ("Homework 9: Serverless Deep Learning", "2024-12-11T23:00:00+00:00"),
            ("Homework 10: Kubernetes and TensorFlow Serving", "2024-12-20T23:00:00+00:00"),
            ("ML Zoomcamp 2024 Competition", "2025-02-10T23:00:00+00:00"),
            ("Article", "2025-02-10T23:00:00+00:00"),
        ],
        "projects": [
            ("Midterm Project", "2024-12-06T23:00:00+00:00"),
            ("Capstone 1", "2025-01-20T23:00:00+00:00"),
            ("Capstone 2", "2025-02-10T23:00:00+00:00"),
        ],
    },
    {
        "slug": "llm-zoomcamp-2024",
        "title": "LLM Zoomcamp 2024",
        "finished": True,
        "homeworks": [
            ("Saturn Cloud", "2024-06-24T23:00:00+00:00"),
            ("Homework 1: Introduction", "2024-07-01T23:00:00+00:00"),
            ("Homework 2: Open-Source LLMs", "2024-07-08T23:00:00+00:00"),
            ("Homework 3: Vector Search", "2024-07-18T23:00:00+00:00"),
            ("Workshop: Open-Source Data Ingestion for RAGs with dlt", "2024-07-28T23:00:00+00:00"),
            ("Homework 4: Evaluation and monitoring", "2024-08-05T23:00:00+00:00"),
            ("Homework 5: Ingestion pipeline", "2024-08-19T23:00:00+00:00"),
            ("LLM Zoomcamp 2024 Competition", "2024-10-14T23:00:00+00:00"),
        ],
        "projects": [
            ("Project attempt 1", "2024-09-23T23:00:00+00:00"),
            ("Project attempt 2", "2024-10-14T23:00:00+00:00"),
            ("Project attempt 3", "2024-11-04T23:00:00+00:00"),
        ],
    },
    {
        "slug": "mlops-zoomcamp-2024",
        "title": "MLOps Zoomcamp 2024",
        "finished": True,
        "homeworks": [
            ("Homework 1: Introduction", "2024-05-23T23:00:00+00:00"),
            ("Homework 2: Experiment Tracking", "2024-05-29T23:00:00+00:00"),
            ("Homework 3: Training Pipelines", "2024-06-10T23:00:00+00:00"),
            ("Homework 4: Deployment", "2024-06-17T23:00:00+00:00"),
            ("Homework 5: Monitoring", "2024-06-27T23:00:00+00:00"),
            ("Homework 6: Best Practices", "2024-07-08T23:00:00+00:00"),
        ],
        "projects": [
            ("Project attempt 1", "2024-08-01T23:00:00+00:00"),
            ("Project attempt 2", "2024-08-26T23:00:00+00:00"),
        ],
    },
    {
        "slug": "sma-zoomcamp-2024",
        "title": "Stock Markets Analytics Zoomcamp 2024",
        "finished": True,
        "homeworks": [
            ("Homework 1: Intro and Data Sources", "2024-04-24T23:59:59+00:00"),
            ("Homework 2: Working with Data in Pandas", "2024-05-09T23:59:59+00:00"),
            ("Homework 3: Modeling for Financial Time Series", "2024-05-26T23:59:59+00:00"),
            ("Homework 4: Trading Simulation", "2024-06-16T23:59:59+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2024-07-22T23:59:59+00:00"),
            ("Project Attempt 2", "2024-08-19T23:59:59+00:00"),
        ],
    },
    {
        "slug": "de-zoomcamp-2024",
        "title": "Data Engineering Zoomcamp 2024",
        "finished": True,
        "homeworks": [
            ("Homework 1: Pre-Requisites (Docker, Terraform, SQL)", "2024-01-31T23:00:00+00:00"),
            ("Homework 2: Mage", "2024-02-08T23:00:00+00:00"),
            ("Homework 3: Data Warehouse", "2024-02-14T23:00:00+00:00"),
            ("Homework 4: Analytics Engineering", "2024-02-24T23:00:00+00:00"),
            ("Workshop 1: Data Ingestion", "2024-02-26T23:00:00+00:00"),
            ("Homework 5: Batch processing", "2024-03-06T23:00:00+00:00"),
            ("Workshop 2: Streaming with SQL", "2024-03-18T23:00:00+00:00"),
            ("Homework 6: Streaming", "2024-04-08T23:00:00+00:00"),
            ("Public Leaderboard", "2024-05-07T23:00:00+00:00"),
        ],
        "projects": [
            ("Project Attempt 1", "2024-04-08T23:00:00+00:00"),
            ("Project Attempt 2", "2024-04-28T23:00:00+00:00"),
        ],
    },
]


def parse_date(value):
    return datetime.fromisoformat(value)


def stable_slug(prefix, title, index):
    return f"{prefix}-{index:02d}-{slugify(title)[:45]}"


def course_description(spec):
    parts = [
        "Free course with practical lessons",
        f"{len(spec['homeworks'])} homework assignments",
    ]
    if spec["projects"]:
        parts.append(f"{len(spec['projects'])} project attempts")
    return f"{', '.join(parts)} for {spec['title']}."


def homework_description(title):
    return (
        f"Practice assignment for {title}. "
        "Use it to check your understanding before moving to the next module."
    )


def ensure_homework_questions(homework):
    question_specs = [
        {
            "text": f"What is the primary goal of {homework.title}?",
            "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
            "answer_type": None,
            "possible_answers": "\n".join(
                [
                    "Complete the assignment deliverables",
                    "Skip the hands-on work",
                    "Only read the course notes",
                    "Submit an unrelated project",
                ]
            ),
            "correct_answer": "1",
        },
        {
            "text": "Which items are usually part of a complete submission?",
            "question_type": QuestionTypes.CHECKBOXES.value,
            "answer_type": None,
            "possible_answers": "\n".join(
                [
                    "Working code or commands",
                    "An empty repository",
                    "Answers for the required tasks",
                    "Unrelated screenshots",
                ]
            ),
            "correct_answer": "1,3",
        },
        {
            "text": "What should a short written answer include?",
            "question_type": QuestionTypes.FREE_FORM.value,
            "answer_type": AnswerTypes.CONTAINS_STRING.value,
            "possible_answers": "",
            "correct_answer": "explanation",
        },
    ]

    for question_spec in question_specs:
        Question.objects.update_or_create(
            homework=homework,
            text=question_spec["text"],
            defaults={
                "question_type": question_spec["question_type"],
                "answer_type": question_spec["answer_type"],
                "possible_answers": question_spec["possible_answers"],
                "correct_answer": question_spec["correct_answer"],
                "scores_for_correct_answer": 1,
            },
        )


def list_courses():
    for spec in COURSE_SPECS:
        selected = "selected" if spec["slug"] in DEFAULT_SELECTED_COURSES else "catalog"
        print(
            f"{spec['slug']} | {spec['title']} | "
            f"{len(spec['homeworks'])} homeworks | "
            f"{len(spec['projects'])} projects | {selected}"
        )
        for title, _due_date in spec["homeworks"]:
            print(f"  - {title}")


def ensure_full_catalog():
    for spec in COURSE_SPECS:
        course, homeworks, projects = ensure_course_materials(spec)
        print(
            f"{course.slug}: catalog ready "
            f"({len(homeworks)} homeworks, {len(projects)} projects)"
        )
    hide_legacy_demo_duplicates()


def hide_legacy_demo_duplicates():
    production_titles = {
        spec["title"]
        for spec in COURSE_SPECS
    }
    updated = Course.objects.filter(
        slug__startswith="demo-",
        title__in=production_titles,
        visible=True,
    ).update(visible=False)
    if updated:
        print(f"hid {updated} legacy demo course duplicates")


def ensure_course_materials(spec):
    due_dates = [
        parse_date(due_date)
        for _, due_date in [*spec["homeworks"], *spec["projects"]]
    ]
    start_date = min(due_dates).date()
    end_date = max(due_dates).date()

    course, _ = Course.objects.update_or_create(
        slug=spec["slug"],
        defaults={
            "title": spec["title"],
            "description": course_description(spec),
            "start_date": start_date,
            "end_date": end_date,
            "registration_url": (
                f"https://courses.datatalks.club/{spec['slug']}/register"
            ),
            "github_repo_url": (
                f"https://github.com/DataTalksClub/{spec['slug']}"
            ),
            "finished": spec["finished"],
            "visible": True,
            "first_homework_scored": True,
        },
    )

    homeworks = []
    for index, (title, due_date) in enumerate(spec["homeworks"], start=1):
        homework, _ = Homework.objects.update_or_create(
            course=course,
            slug=stable_slug("homework", title, index),
            defaults={
                "title": title,
                "description": homework_description(title),
                "due_date": parse_date(due_date),
                "state": HomeworkState.SCORED.value,
            },
        )
        ensure_homework_questions(homework)
        homeworks.append(homework)

    projects = []
    for index, (title, due_date) in enumerate(spec["projects"], start=1):
        project, _ = Project.objects.update_or_create(
            course=course,
            slug=stable_slug("project", title, index),
            defaults={
                "title": title,
                "description": f"Production-like generated project: {title}",
                "submission_due_date": parse_date(due_date),
                "peer_review_due_date": parse_date(due_date),
                "state": ProjectState.COMPLETED.value,
            },
        )
        projects.append(project)

    return course, homeworks, projects


def score_for_student(student_index, count, assignment_index, max_score):
    base = count - student_index + 1
    spread = max_score - ((student_index * assignment_index) % 17)
    completion_penalty = 0
    if student_index % (assignment_index + 7) == 0:
        completion_penalty = max_score // 3
    return max(0, min(max_score, (base * max_score // count) + spread // 4 - completion_penalty))


def seed_course(spec, count):
    course, homeworks, projects = ensure_course_materials(spec)
    username_prefix = f"{USER_PREFIX}-{course.slug}-"

    enrollments = []
    created_users = 0
    created_enrollments = 0

    for student_index in range(1, count + 1):
        username = f"{username_prefix}{student_index:04d}"
        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.com"},
        )
        created_users += int(user_created)

        enrollment, enrollment_created = Enrollment.objects.get_or_create(
            course=course,
            student=user,
            defaults={"display_name": f"{spec['title']} Student {student_index:04d}"},
        )
        created_enrollments += int(enrollment_created)

        enrollment.display_name = f"{spec['title']} Student {student_index:04d}"
        enrollment.display_on_leaderboard = True
        enrollments.append(enrollment)

    Enrollment.objects.bulk_update(
        enrollments,
        ["display_name", "display_on_leaderboard"],
    )

    generated_enrollments = Enrollment.objects.filter(
        course=course,
        student__username__startswith=username_prefix,
    )

    Submission.objects.filter(
        enrollment__in=generated_enrollments,
        homework__in=homeworks,
    ).delete()
    ProjectSubmission.objects.filter(
        enrollment__in=generated_enrollments,
        project__in=projects,
    ).delete()

    homework_submissions = []
    project_submissions = []

    for student_index, enrollment in enumerate(enrollments, start=1):
        for homework_index, homework in enumerate(homeworks, start=1):
            questions_score = score_for_student(student_index, count, homework_index, 100)
            faq_score = (student_index + homework_index) % 6
            lip_score = (student_index * homework_index) % 8
            if student_index % (homework_index + 11) == 0:
                questions_score = 0
                faq_score = 0
                lip_score = 0

            homework_submissions.append(
                Submission(
                    homework=homework,
                    student=enrollment.student,
                    enrollment=enrollment,
                    homework_link=(
                        f"https://example.com/{course.slug}/"
                        f"{student_index:04d}/homework-{homework_index}"
                    ),
                    learning_in_public_links=[
                        (
                            f"https://example.com/{course.slug}/"
                            f"{student_index:04d}/notes/homework-{homework_index}"
                        )
                    ],
                    time_spent_lectures=1.5 + ((student_index + homework_index) % 8),
                    time_spent_homework=2.0 + ((student_index * homework_index) % 10),
                    faq_contribution=(
                        "Generated FAQ note"
                        if (student_index + homework_index) % 5 == 0
                        else ""
                    ),
                    questions_score=questions_score,
                    faq_score=faq_score,
                    learning_in_public_score=lip_score,
                    total_score=questions_score + faq_score + lip_score,
                )
            )

        for project_index, project in enumerate(projects, start=1):
            project_score = score_for_student(student_index, count, project_index, 240)
            project_faq_score = (student_index + project_index) % 10
            project_lip_score = (student_index * project_index) % 15
            peer_review_score = 20 + ((student_index + project_index) % 11)
            peer_review_lip_score = (student_index + project_index) % 3
            if student_index % (project_index + 13) == 0:
                project_score = 0
                project_faq_score = 0
                project_lip_score = 0
                peer_review_score = 0
                peer_review_lip_score = 0

            project_submissions.append(
                ProjectSubmission(
                    project=project,
                    student=enrollment.student,
                    enrollment=enrollment,
                    github_link=(
                        f"https://github.com/example/{course.slug}-"
                        f"{student_index:04d}-project-{project_index}"
                    ),
                    commit_id=f"{student_index:036d}{project_index:04d}"[:40],
                    learning_in_public_links=[
                        (
                            f"https://example.com/{course.slug}/"
                            f"{student_index:04d}/notes/project-{project_index}"
                        )
                    ],
                    faq_contribution=(
                        "Generated project FAQ note"
                        if (student_index + project_index) % 4 == 0
                        else ""
                    ),
                    time_spent=6.0 + ((student_index * project_index) % 24),
                    problems_comments="Generated project submission",
                    project_score=project_score,
                    project_faq_score=project_faq_score,
                    project_learning_in_public_score=project_lip_score,
                    peer_review_score=peer_review_score,
                    peer_review_learning_in_public_score=peer_review_lip_score,
                    total_score=(
                        project_score
                        + project_faq_score
                        + project_lip_score
                        + peer_review_score
                        + peer_review_lip_score
                    ),
                    reviewed_enough_peers=peer_review_score > 0,
                    passed=project_score > 0,
                )
            )

    Submission.objects.bulk_create(homework_submissions, batch_size=1000)
    ProjectSubmission.objects.bulk_create(project_submissions, batch_size=1000)

    for homework in homeworks:
        calculate_homework_statistics(homework, force=True)
    for project in projects:
        calculate_project_statistics(project, force=True)

    update_leaderboard(course)
    cache.delete(f"leaderboard:{course.id}")
    cache.delete(f"leaderboard_data:{course.id}")
    cache.delete(f"leaderboard_yaml:{course.id}")

    top = (
        Enrollment.objects.filter(course=course)
        .order_by("position_on_leaderboard")
        .values_list("display_name", "total_score", "position_on_leaderboard")
        .first()
    )

    print(
        f"{course.slug}: {created_users} users created, "
        f"{created_enrollments} enrollments created, "
        f"{len(homework_submissions)} homework submissions, "
        f"{len(project_submissions)} project submissions, top={top}"
    )


def main():
    configure_sqlite_busy_timeout()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list-courses",
        action="store_true",
        help="Print the production-derived course catalog and exit.",
    )
    parser.add_argument(
        "--course",
        action="append",
        choices=[spec["slug"] for spec in COURSE_SPECS],
        help="Course slug to seed. Can be passed multiple times.",
    )
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Create/update all production-derived courses, homeworks, and projects without generating participants.",
    )
    parser.add_argument(
        "--count",
        type=int,
        help="Override generated participant count for every selected course.",
    )
    args = parser.parse_args()

    if args.list_courses:
        list_courses()
        return

    run_with_lock_retries(ensure_full_catalog)
    if args.catalog_only:
        return

    specs_by_slug = {spec["slug"]: spec for spec in COURSE_SPECS}
    selected_slugs = args.course or list(DEFAULT_SELECTED_COURSES)

    for slug in selected_slugs:
        count = args.count or DEFAULT_SELECTED_COURSES.get(slug, 300)
        run_with_lock_retries(lambda slug=slug, count=count: seed_course(specs_by_slug[slug], count))


if __name__ == "__main__":
    main()
