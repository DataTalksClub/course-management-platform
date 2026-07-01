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
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_path = str(ROOT)
sys.path.insert(0, root_path)
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
from courses.assignment_statistics import (
    calculate_homework_statistics,
    calculate_project_statistics,
)
from courses.leaderboard import update_leaderboard


USER_PREFIX = "production-like-user"

DEFAULT_SELECTED_COURSES = {
    "de-zoomcamp-2026": 1200,
    "ml-zoomcamp-2025": 1000,
    "llm-zoomcamp-2025": 800,
    "mlops-zoomcamp-2025": 650,
    "sma-zoomcamp-2025": 450,
}


@dataclass(frozen=True)
class CourseMaterials:
    course: Course
    homeworks: list[Homework]
    projects: list[Project]


@dataclass(frozen=True)
class GeneratedSubmissionData:
    course: Course
    enrollment: Enrollment
    student_index: int
    item_index: int
    item: object
    count: int


@dataclass(frozen=True)
class GeneratedSubmissionsData:
    course: Course
    enrollments: list[Enrollment]
    homeworks: list[Homework]
    projects: list[Project]
    count: int


@dataclass(frozen=True)
class GeneratedEnrollmentData:
    course: Course
    spec: dict
    count: int
    username_prefix: str


@dataclass(frozen=True)
class GeneratedEnrollmentResult:
    enrollments: list[Enrollment]
    created_users: int
    created_enrollments: int


@dataclass(frozen=True)
class GeneratedEnrollmentRecord:
    enrollment: Enrollment
    user_created: bool
    enrollment_created: bool


@dataclass(frozen=True)
class GeneratedSubmissionResult:
    homework_submissions: list[Submission]
    project_submissions: list[ProjectSubmission]


@dataclass(frozen=True)
class SeedSummaryData:
    course: Course
    created_users: int
    created_enrollments: int
    homework_submissions: list[Submission]
    project_submissions: list[ProjectSubmission]


@dataclass(frozen=True)
class GeneratedProjectScores:
    project_score: int
    project_faq_score: int
    project_lip_score: int
    peer_review_score: int
    peer_review_lip_score: int

    @property
    def total_score(self) -> int:
        return (
            self.project_score
            + self.project_faq_score
            + self.project_lip_score
            + self.peer_review_score
            + self.peer_review_lip_score
        )


@dataclass(frozen=True)
class GeneratedHomeworkScores:
    questions_score: int
    faq_score: int
    lip_score: int

    @property
    def total_score(self) -> int:
        return self.questions_score + self.faq_score + self.lip_score


@dataclass(frozen=True)
class GeneratedHomeworkLinks:
    homework_link: str
    learning_in_public_link: str


@dataclass(frozen=True)
class GeneratedHomeworkTimeSpent:
    lectures: float
    homework: float


@dataclass(frozen=True)
class GeneratedHomeworkSubmissionValues:
    scores: GeneratedHomeworkScores
    links: GeneratedHomeworkLinks
    time_spent: GeneratedHomeworkTimeSpent
    faq_contribution_url: str
    learning_in_public_links: list[str]


@dataclass(frozen=True)
class GeneratedProjectSubmissionValues:
    scores: GeneratedProjectScores
    github_link: str
    commit_id: str
    learning_in_public_links: list[str]
    faq_contribution_url: str
    time_spent: float
    reviewed_enough_peers: bool
    passed: bool


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


def homework_question_specs(homework):
    primary_goal_question = primary_goal_question_spec(homework)
    complete_submission_question = complete_submission_question_spec()
    written_answer_question = written_answer_question_spec()
    return [
        primary_goal_question,
        complete_submission_question,
        written_answer_question,
    ]


def primary_goal_question_spec(homework):
    possible_answers = "\n".join(
        [
            "Complete the assignment deliverables",
            "Skip the hands-on work",
            "Only read the course notes",
            "Submit an unrelated project",
        ]
    )
    return {
        "text": f"What is the primary goal of {homework.title}?",
        "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
        "answer_type": None,
        "possible_answers": possible_answers,
        "correct_answer": "1",
    }


def complete_submission_question_spec():
    possible_answers = "\n".join(
        [
            "Working code or commands",
            "An empty repository",
            "Answers for the required tasks",
            "Unrelated screenshots",
        ]
    )
    return {
        "text": "Which items are usually part of a complete submission?",
        "question_type": QuestionTypes.CHECKBOXES.value,
        "answer_type": None,
        "possible_answers": possible_answers,
        "correct_answer": "1,3",
    }


def written_answer_question_spec():
    return {
        "text": "What should a short written answer include?",
        "question_type": QuestionTypes.FREE_FORM.value,
        "answer_type": AnswerTypes.CONTAINS_STRING.value,
        "possible_answers": "",
        "correct_answer": "explanation",
    }


def ensure_homework_questions(homework):
    question_specs = homework_question_specs(homework)
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
        homework_specs = spec["homeworks"]
        for title, _due_date in homework_specs:
            print(f"  - {title}")


def ensure_full_catalog():
    for spec in COURSE_SPECS:
        materials = ensure_course_materials(spec)
        print(
            f"{materials.course.slug}: catalog ready "
            f"({len(materials.homeworks)} homeworks, "
            f"{len(materials.projects)} projects)"
        )
    hide_legacy_demo_duplicates()


def hide_legacy_demo_duplicates():
    production_titles = set()
    for spec in COURSE_SPECS:
        title = spec["title"]
        production_titles.add(title)
    updated = Course.objects.filter(
        slug__startswith="demo-",
        title__in=production_titles,
        visible=True,
    ).update(visible=False)
    if updated:
        print(f"hid {updated} legacy demo course duplicates")


def course_due_range(spec):
    due_dates = []
    assignment_specs = []
    homework_specs = spec["homeworks"]
    for homework_spec in homework_specs:
        assignment_specs.append(homework_spec)
    project_specs = spec["projects"]
    for project_spec in project_specs:
        assignment_specs.append(project_spec)
    for _title, due_date in assignment_specs:
        parsed_due_date = parse_date(due_date)
        due_dates.append(parsed_due_date)
    start_date = min(due_dates).date()
    end_date = max(due_dates).date()
    return start_date, end_date


def ensure_course(spec):
    start_date, end_date = course_due_range(spec)
    description = course_description(spec)
    registration_url = f"https://courses.datatalks.club/{spec['slug']}/register"
    github_repo_url = f"https://github.com/DataTalksClub/{spec['slug']}"
    course, _ = Course.objects.update_or_create(
        slug=spec["slug"],
        defaults={
            "title": spec["title"],
            "description": description,
            "start_date": start_date,
            "end_date": end_date,
            "registration_url": registration_url,
            "github_repo_url": github_repo_url,
            "finished": spec["finished"],
            "visible": True,
            "first_homework_scored": True,
        },
    )
    return course


def ensure_homeworks(course, spec):
    homeworks = []
    for index, (title, due_date) in enumerate(spec["homeworks"], start=1):
        homework_slug = stable_slug("homework", title, index)
        description = homework_description(title)
        parsed_due_date = parse_date(due_date)
        homework, _ = Homework.objects.update_or_create(
            course=course,
            slug=homework_slug,
            defaults={
                "title": title,
                "description": description,
                "due_date": parsed_due_date,
                "state": HomeworkState.SCORED.value,
            },
        )
        ensure_homework_questions(homework)
        homeworks.append(homework)
    return homeworks


def ensure_projects(course, spec):
    projects = []
    for index, (title, due_date) in enumerate(spec["projects"], start=1):
        project_slug = stable_slug("project", title, index)
        description = f"Production-like generated project: {title}"
        parsed_due_date = parse_date(due_date)
        project, _ = Project.objects.update_or_create(
            course=course,
            slug=project_slug,
            defaults={
                "title": title,
                "description": description,
                "submission_due_date": parsed_due_date,
                "peer_review_due_date": parsed_due_date,
                "state": ProjectState.COMPLETED.value,
            },
        )
        projects.append(project)
    return projects


def ensure_course_materials(spec):
    course = ensure_course(spec)
    homeworks = ensure_homeworks(course, spec)
    projects = ensure_projects(course, spec)

    return CourseMaterials(
        course=course,
        homeworks=homeworks,
        projects=projects,
    )


def score_for_student(student_index, count, assignment_index, max_score):
    base = count - student_index + 1
    spread = max_score - ((student_index * assignment_index) % 17)
    completion_penalty = 0
    if student_index % (assignment_index + 7) == 0:
        completion_penalty = max_score // 3
    raw_score = (base * max_score // count) + spread // 4 - completion_penalty
    capped_score = min(max_score, raw_score)
    return max(0, capped_score)


def generated_display_name(data, student_index):
    return f"{data.spec['title']} Student {student_index:04d}"


def create_generated_enrollment(data, student_index):
    username = f"{data.username_prefix}{student_index:04d}"
    user_defaults = {"email": f"{username}@example.com"}
    user, user_created = User.objects.get_or_create(
        username=username,
        defaults=user_defaults,
    )

    display_name = generated_display_name(data, student_index)
    enrollment_defaults = {"display_name": display_name}
    enrollment, enrollment_created = Enrollment.objects.get_or_create(
        course=data.course,
        student=user,
        defaults=enrollment_defaults,
    )
    enrollment.display_name = display_name
    enrollment.display_on_leaderboard = True

    return GeneratedEnrollmentRecord(
        enrollment=enrollment,
        user_created=user_created,
        enrollment_created=enrollment_created,
    )


def create_generated_enrollments(data):
    enrollments = []
    created_users = 0
    created_enrollments = 0

    for student_index in range(1, data.count + 1):
        record = create_generated_enrollment(data, student_index)
        created_users += int(record.user_created)
        created_enrollments += int(record.enrollment_created)
        enrollments.append(record.enrollment)

    Enrollment.objects.bulk_update(
        enrollments,
        ["display_name", "display_on_leaderboard"],
    )

    return GeneratedEnrollmentResult(
        enrollments=enrollments,
        created_users=created_users,
        created_enrollments=created_enrollments,
    )


def generated_enrollment_queryset(course, username_prefix):
    return Enrollment.objects.filter(
        course=course,
        student__username__startswith=username_prefix,
    )


def clear_generated_submissions(generated_enrollments, homeworks, projects):
    Submission.objects.filter(
        enrollment__in=generated_enrollments,
        homework__in=homeworks,
    ).delete()
    ProjectSubmission.objects.filter(
        enrollment__in=generated_enrollments,
        project__in=projects,
    ).delete()


def homework_scores(student_index, count, homework_index):
    questions_score = score_for_student(student_index, count, homework_index, 100)
    faq_score = (student_index + homework_index) % 6
    lip_score = (student_index * homework_index) % 8
    if student_index % (homework_index + 11) == 0:
        return GeneratedHomeworkScores(
            questions_score=0,
            faq_score=0,
            lip_score=0,
        )
    return GeneratedHomeworkScores(
        questions_score=questions_score,
        faq_score=faq_score,
        lip_score=lip_score,
    )


def homework_faq_url(student_index, homework_index, faq_score):
    if not faq_score:
        return ""
    return (
        "https://github.com/DataTalksClub/faq/issues/"
        f"{10000 + student_index * 10 + homework_index}"
    )


def generated_homework_links(data):
    base_url = (
        f"https://example.com/{data.course.slug}/"
        f"{data.student_index:04d}"
    )
    return GeneratedHomeworkLinks(
        homework_link=f"{base_url}/homework-{data.item_index}",
        learning_in_public_link=(
            f"{base_url}/notes/homework-{data.item_index}"
        ),
    )


def generated_homework_time_spent(data):
    lectures = 1.5 + ((data.student_index + data.item_index) % 8)
    homework = 2.0 + ((data.student_index * data.item_index) % 10)
    return GeneratedHomeworkTimeSpent(
        lectures=lectures,
        homework=homework,
    )


def homework_learning_in_public_links(links):
    learning_in_public_links = []
    learning_in_public_links.append(links.learning_in_public_link)
    return learning_in_public_links


def homework_submission_values(data):
    scores = homework_scores(
        data.student_index,
        data.count,
        data.item_index,
    )
    links = generated_homework_links(data)
    time_spent = generated_homework_time_spent(data)
    faq_contribution_url = homework_faq_url(
        data.student_index,
        data.item_index,
        scores.faq_score,
    )
    learning_in_public_links = homework_learning_in_public_links(links)
    return GeneratedHomeworkSubmissionValues(
        scores=scores,
        links=links,
        time_spent=time_spent,
        faq_contribution_url=faq_contribution_url,
        learning_in_public_links=learning_in_public_links,
    )


def build_homework_submission(data):
    values = homework_submission_values(data)

    return Submission(
        homework=data.item,
        student=data.enrollment.student,
        enrollment=data.enrollment,
        homework_link=values.links.homework_link,
        learning_in_public_links=values.learning_in_public_links,
        time_spent_lectures=values.time_spent.lectures,
        time_spent_homework=values.time_spent.homework,
        faq_contribution_url=values.faq_contribution_url,
        questions_score=values.scores.questions_score,
        faq_score=values.scores.faq_score,
        learning_in_public_score=values.scores.lip_score,
        total_score=values.scores.total_score,
    )


def project_scores(student_index, count, project_index):
    project_score = score_for_student(student_index, count, project_index, 240)
    project_faq_score = (student_index + project_index) % 10
    project_lip_score = (student_index * project_index) % 15
    peer_review_score = 20 + ((student_index + project_index) % 11)
    peer_review_lip_score = (student_index + project_index) % 3
    if student_index % (project_index + 13) == 0:
        return GeneratedProjectScores(
            project_score=0,
            project_faq_score=0,
            project_lip_score=0,
            peer_review_score=0,
            peer_review_lip_score=0,
        )
    return GeneratedProjectScores(
        project_score=project_score,
        project_faq_score=project_faq_score,
        project_lip_score=project_lip_score,
        peer_review_score=peer_review_score,
        peer_review_lip_score=peer_review_lip_score,
    )


def project_faq_url(student_index, project_index, project_faq_score):
    if not project_faq_score:
        return ""
    return (
        "https://github.com/DataTalksClub/faq/pull/"
        f"{20000 + student_index * 10 + project_index}"
    )


def project_github_link(data):
    return (
        f"https://github.com/example/{data.course.slug}-"
        f"{data.student_index:04d}-project-{data.item_index}"
    )


def project_commit_id(data):
    return f"{data.student_index:036d}{data.item_index:04d}"[:40]


def project_learning_links(data):
    return [
        (
            f"https://example.com/{data.course.slug}/"
            f"{data.student_index:04d}/notes/project-{data.item_index}"
        )
    ]


def project_submission_values(data):
    scores = project_scores(
        data.student_index,
        data.count,
        data.item_index,
    )
    github_link = project_github_link(data)
    commit_id = project_commit_id(data)
    learning_in_public_links = project_learning_links(data)
    faq_contribution_url = project_faq_url(
        data.student_index,
        data.item_index,
        scores.project_faq_score,
    )
    time_spent = 6.0 + ((data.student_index * data.item_index) % 24)
    reviewed_enough_peers = scores.peer_review_score > 0
    passed = scores.project_score > 0
    return GeneratedProjectSubmissionValues(
        scores=scores,
        github_link=github_link,
        commit_id=commit_id,
        learning_in_public_links=learning_in_public_links,
        faq_contribution_url=faq_contribution_url,
        time_spent=time_spent,
        reviewed_enough_peers=reviewed_enough_peers,
        passed=passed,
    )


def build_project_submission(data):
    values = project_submission_values(data)
    return ProjectSubmission(
        project=data.item,
        student=data.enrollment.student,
        enrollment=data.enrollment,
        github_link=values.github_link,
        commit_id=values.commit_id,
        learning_in_public_links=values.learning_in_public_links,
        faq_contribution_url=values.faq_contribution_url,
        time_spent=values.time_spent,
        problems_comments="Generated project submission",
        project_score=values.scores.project_score,
        project_faq_score=values.scores.project_faq_score,
        project_learning_in_public_score=values.scores.project_lip_score,
        peer_review_score=values.scores.peer_review_score,
        peer_review_learning_in_public_score=(
            values.scores.peer_review_lip_score
        ),
        total_score=values.scores.total_score,
        reviewed_enough_peers=values.reviewed_enough_peers,
        passed=values.passed,
    )


def build_generated_submissions(data):
    homework_submissions = []
    project_submissions = []
    for student_index, enrollment in enumerate(data.enrollments, start=1):
        for homework_index, homework in enumerate(data.homeworks, start=1):
            submission_data = GeneratedSubmissionData(
                course=data.course,
                enrollment=enrollment,
                student_index=student_index,
                item_index=homework_index,
                item=homework,
                count=data.count,
            )
            homework_submission = build_homework_submission(submission_data)
            homework_submissions.append(homework_submission)
        for project_index, project in enumerate(data.projects, start=1):
            submission_data = GeneratedSubmissionData(
                course=data.course,
                enrollment=enrollment,
                student_index=student_index,
                item_index=project_index,
                item=project,
                count=data.count,
            )
            project_submission = build_project_submission(submission_data)
            project_submissions.append(project_submission)
    return homework_submissions, project_submissions


def recalculate_course_scores(course, homeworks, projects):
    for homework in homeworks:
        calculate_homework_statistics(homework, force=True)
    for project in projects:
        calculate_project_statistics(project, force=True)

    update_leaderboard(course)
    cache.delete(f"leaderboard:{course.id}")
    cache.delete(f"leaderboard_data:{course.id}")
    cache.delete(f"leaderboard_yaml:{course.id}")


def top_leaderboard_entry(course):
    return (
        Enrollment.objects.filter(course=course)
        .order_by("position_on_leaderboard")
        .values_list("display_name", "total_score", "position_on_leaderboard")
        .first()
    )


def print_seed_summary(data):
    top = top_leaderboard_entry(data.course)
    print(
        f"{data.course.slug}: {data.created_users} users created, "
        f"{data.created_enrollments} enrollments created, "
        f"{len(data.homework_submissions)} homework submissions, "
        f"{len(data.project_submissions)} project submissions, top={top}"
    )


def generated_enrollment_result(materials, spec, count, username_prefix):
    enrollment_data = GeneratedEnrollmentData(
        course=materials.course,
        spec=spec,
        count=count,
        username_prefix=username_prefix,
    )
    return create_generated_enrollments(enrollment_data)


def persist_generated_submissions(materials, enrollment_result, count):
    generated_data = GeneratedSubmissionsData(
        course=materials.course,
        enrollments=enrollment_result.enrollments,
        homeworks=materials.homeworks,
        projects=materials.projects,
        count=count,
    )
    homework_submissions, project_submissions = (
        build_generated_submissions(generated_data)
    )
    Submission.objects.bulk_create(homework_submissions, batch_size=1000)
    ProjectSubmission.objects.bulk_create(project_submissions, batch_size=1000)
    return GeneratedSubmissionResult(
        homework_submissions=homework_submissions,
        project_submissions=project_submissions,
    )


def clear_generated_course_submissions(materials, username_prefix):
    generated_enrollments = generated_enrollment_queryset(
        materials.course,
        username_prefix,
    )
    clear_generated_submissions(
        generated_enrollments,
        materials.homeworks,
        materials.projects,
    )


def seed_course(spec, count):
    materials = ensure_course_materials(spec)
    username_prefix = f"{USER_PREFIX}-{materials.course.slug}-"
    enrollment_result = generated_enrollment_result(
        materials,
        spec,
        count,
        username_prefix,
    )
    clear_generated_course_submissions(materials, username_prefix)
    submission_result = persist_generated_submissions(
        materials,
        enrollment_result,
        count,
    )
    recalculate_course_scores(
        materials.course,
        materials.homeworks,
        materials.projects,
    )
    summary_data = SeedSummaryData(
        course=materials.course,
        created_users=enrollment_result.created_users,
        created_enrollments=enrollment_result.created_enrollments,
        homework_submissions=submission_result.homework_submissions,
        project_submissions=submission_result.project_submissions,
    )
    print_seed_summary(summary_data)


def parse_args():
    parser = argparse.ArgumentParser()
    course_slugs = []
    for spec in COURSE_SPECS:
        slug = spec["slug"]
        course_slugs.append(slug)
    parser.add_argument(
        "--list-courses",
        action="store_true",
        help="Print the production-derived course catalog and exit.",
    )
    parser.add_argument(
        "--course",
        action="append",
        choices=course_slugs,
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
    return parser.parse_args()


def seed_selected_courses(args):
    specs_by_slug = {}
    for spec in COURSE_SPECS:
        slug = spec["slug"]
        specs_by_slug[slug] = spec
    selected_slugs = args.course or list(DEFAULT_SELECTED_COURSES)

    for slug in selected_slugs:
        count = args.count or DEFAULT_SELECTED_COURSES.get(slug, 300)
        callback = partial(seed_selected_course, specs_by_slug, slug, count)
        run_with_lock_retries(callback)


def seed_selected_course(specs_by_slug, slug, count):
    spec = specs_by_slug[slug]
    seed_course(spec, count)


def main():
    configure_sqlite_busy_timeout()
    args = parse_args()

    if args.list_courses:
        list_courses()
        return

    run_with_lock_retries(ensure_full_catalog)
    if args.catalog_only:
        return

    seed_selected_courses(args)


if __name__ == "__main__":
    main()
