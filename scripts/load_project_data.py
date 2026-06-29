#!/usr/bin/env python
"""
Script to load project data from a JSONL file into a local database.
This allows reproducing scoring bugs locally with production data.

Usage:
    uv run python scripts/load_project_data.py \
        --file data_prod/project_data_ml-zoomcamp-2025_midterm_20251130_121004.jsonl
"""

import os
import sys
import json
import argparse
from dataclasses import dataclass, field
from datetime import datetime
from tqdm import tqdm

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
    PeerReview,
    ReviewCriteria,
    CriteriaResponse,
    ProjectEvaluationScore,
)

User = get_user_model()


def parse_datetime(dt_str):
    """Parse datetime string"""
    if dt_str is None:
        return None
    return datetime.fromisoformat(dt_str)


@dataclass
class ProjectImportData:
    metadata: dict | None = None
    course: dict | None = None
    project: dict | None = None
    users: list[dict] = field(default_factory=list)
    enrollments: list[dict] = field(default_factory=list)
    review_criteria: list[dict] = field(default_factory=list)
    submissions: list[dict] = field(default_factory=list)
    peer_reviews: list[dict] = field(default_factory=list)
    criteria_responses: list[dict] = field(default_factory=list)
    evaluation_scores: list[dict] = field(default_factory=list)


@dataclass
class ImportMaps:
    user_id_map: dict = field(default_factory=dict)
    enrollment_id_map: dict = field(default_factory=dict)
    criteria_id_map: dict = field(default_factory=dict)
    submission_id_map: dict = field(default_factory=dict)
    review_id_map: dict = field(default_factory=dict)


SINGULAR_IMPORT_FIELDS = {
    "metadata": "metadata",
    "course": "course",
    "project": "project",
}

LIST_IMPORT_FIELDS = {
    "user": "users",
    "enrollment": "enrollments",
    "review_criteria": "review_criteria",
    "submission": "submissions",
    "peer_review": "peer_reviews",
    "criteria_response": "criteria_responses",
    "evaluation_score": "evaluation_scores",
}


def append_import_record(data: ProjectImportData, record: dict) -> None:
    record_type = record["type"]
    if record_type in SINGULAR_IMPORT_FIELDS:
        setattr(data, SINGULAR_IMPORT_FIELDS[record_type], record_value(record))
    elif record_type in LIST_IMPORT_FIELDS:
        getattr(data, LIST_IMPORT_FIELDS[record_type]).append(record_value(record))


def record_value(record):
    if record["type"] == "metadata":
        return record
    return record["data"]


def count_lines(input_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)


def read_project_import_data(input_file):
    print(f"Loading data from: {input_file}")
    print("-" * 80)
    data = ProjectImportData()
    total_lines = count_lines(input_file)

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, total=total_lines, desc="Reading data", unit="records"):
            append_import_record(data, json.loads(line))

    return data


def print_import_metadata(data: ProjectImportData) -> None:
    print("✓ Read data from file")
    print(f"  Extracted at: {data.metadata['extracted_at']}")
    print(f"  Course: {data.metadata['course_slug']}")
    print(f"  Project: {data.metadata['project_slug']}")
    print()

def course_defaults(course_data):
    return {
        "title": course_data["title"],
        "description": course_data["description"],
        "social_media_hashtag": course_data.get("social_media_hashtag", ""),
        "first_homework_scored": course_data.get("first_homework_scored", False),
        "finished": course_data.get("finished", False),
        "faq_document_url": course_data.get("faq_document_url", ""),
        "min_projects_to_pass": course_data.get("min_projects_to_pass", 1),
        "homework_problems_comments_field": course_data.get(
            "homework_problems_comments_field", False
        ),
        "project_passing_score": course_data.get("project_passing_score", 0),
        "visible": course_data.get("visible", True),
    }


def get_or_create_course(course_data):
    course, created = Course.objects.get_or_create(
        slug=course_data["slug"],
        defaults=course_defaults(course_data),
    )
    if created:
        print(f"✓ Created course: {course.title}")
    else:
        print(f"✓ Course already exists: {course.title}")
    return course


def project_defaults(project_data):
    return {
        "title": project_data["title"],
        "description": project_data["description"],
        "submission_due_date": parse_datetime(project_data["submission_due_date"]),
        "learning_in_public_cap_project": project_data.get(
            "learning_in_public_cap_project", 14
        ),
        "peer_review_due_date": parse_datetime(project_data["peer_review_due_date"]),
        "time_spent_project_field": project_data.get("time_spent_project_field", True),
        "problems_comments_field": project_data.get("problems_comments_field", True),
        "faq_contribution_field": project_data.get("faq_contribution_field", True),
        "learning_in_public_cap_review": project_data.get(
            "learning_in_public_cap_review", 2
        ),
        "number_of_peers_to_evaluate": project_data.get(
            "number_of_peers_to_evaluate", 3
        ),
        "points_for_peer_review": project_data.get("points_for_peer_review", 3),
        "time_spent_evaluation_field": project_data.get(
            "time_spent_evaluation_field", True
        ),
        "state": project_data["state"],
    }


def clear_project_data(project) -> None:
    print("  Clearing existing project data...")
    ProjectEvaluationScore.objects.filter(submission__project=project).delete()
    CriteriaResponse.objects.filter(
        review__submission_under_evaluation__project=project
    ).delete()
    PeerReview.objects.filter(submission_under_evaluation__project=project).delete()
    ProjectSubmission.objects.filter(project=project).delete()
    print("  ✓ Cleared")


def get_or_create_project(course, project_data, clear_existing):
    project, created = Project.objects.get_or_create(
        course=course,
        slug=project_data["slug"],
        defaults=project_defaults(project_data),
    )

    if created:
        print(f"✓ Created project: {project.title}")
        return project, True

    print(f"⚠ Project already exists: {project.title}")
    if clear_existing:
        clear_project_data(project)
        return project, True

    print("  Use --clear-existing to replace data")
    return project, False


def existing_users_by_username(users_data):
    usernames = [user_data["username"] for user_data in users_data]
    return {u.username: u for u in User.objects.filter(username__in=usernames)}


def build_user(user_data):
    return User(
        username=user_data["username"],
        email=user_data["email"],
        certificate_name=user_data.get("certificate_name", ""),
        dark_mode=user_data.get("dark_mode", False),
    )


def pending_user_imports(users_data, existing_users, maps: ImportMaps):
    users_to_create = []
    for user_data in tqdm(users_data, desc="Processing users", unit="users"):
        old_id = user_data["id"]
        username = user_data["username"]
        if username in existing_users:
            maps.user_id_map[old_id] = existing_users[username].id
            continue
        users_to_create.append((old_id, build_user(user_data)))
    return users_to_create


def create_users(users_data, maps: ImportMaps) -> None:
    print(f"\nCreating {len(users_data)} users...")
    existing_users = existing_users_by_username(users_data)
    users_to_create = pending_user_imports(users_data, existing_users, maps)
    bulk_create_mapped(User, users_to_create, maps.user_id_map)

    print(
        "✓ Users ready "
        f"({len(users_to_create)} created, {len(existing_users)} existing)"
    )


def build_enrollment(enroll_data, course, student_id):
    return Enrollment(
        **valid_model_kwargs(
            Enrollment,
            {
                "student_id": student_id,
                "course": course,
                "enrollment_date": parse_datetime(enroll_data["enrollment_date"]),
                "display_name": enroll_data.get("display_name", ""),
                "display_on_leaderboard": enroll_data.get(
                    "display_on_leaderboard", True
                ),
                "position_on_leaderboard": enroll_data.get(
                    "position_on_leaderboard"
                ),
                "certificate_name": enroll_data.get("certificate_name"),
                "total_score": enroll_data.get("total_score", 0),
                "certificate_url": enroll_data.get("certificate_url"),
                "github_url": enroll_data.get("github_url"),
                "linkedin_url": enroll_data.get("linkedin_url"),
                "personal_website_url": enroll_data.get("personal_website_url"),
                "about_me": enroll_data.get("about_me"),
            },
        )
    )


def valid_model_kwargs(model, values):
    field_names = {field.name for field in model._meta.fields}
    attnames = {field.attname for field in model._meta.fields}
    valid_names = field_names | attnames
    return {
        name: value
        for name, value in values.items()
        if name in valid_names
    }


def existing_enrollments_by_student(course, maps: ImportMaps):
    return {
        e.student_id: e for e in Enrollment.objects.filter(
            course=course,
            student_id__in=list(maps.user_id_map.values()),
        )
    }


def pending_enrollment_imports(
    enrollments_data,
    course,
    existing_enrollments,
    maps: ImportMaps,
):
    enrollments_to_create = []
    for enroll_data in tqdm(
        enrollments_data, desc="Processing enrollments", unit="enrollments"
    ):
        old_id = enroll_data["id"]
        new_student_id = maps.user_id_map[enroll_data["student_id"]]
        if new_student_id in existing_enrollments:
            maps.enrollment_id_map[old_id] = existing_enrollments[new_student_id].id
            continue
        enrollment = build_enrollment(enroll_data, course, new_student_id)
        enrollments_to_create.append((old_id, enrollment))
    return enrollments_to_create


def create_enrollments(enrollments_data, course, maps: ImportMaps) -> None:
    print(f"Creating {len(enrollments_data)} enrollments...")
    existing_enrollments = existing_enrollments_by_student(course, maps)
    enrollments_to_create = pending_enrollment_imports(
        enrollments_data,
        course,
        existing_enrollments,
        maps,
    )
    bulk_create_mapped(
        Enrollment,
        enrollments_to_create,
        maps.enrollment_id_map,
    )

    print(
        "✓ Enrollments ready "
        f"({len(enrollments_to_create)} created, "
        f"{len(existing_enrollments)} existing)"
    )


def create_review_criteria(criteria_records, course, maps: ImportMaps) -> None:
    print(f"Creating {len(criteria_records)} review criteria...")
    for criteria_data in criteria_records:
        criteria, _created = ReviewCriteria.objects.get_or_create(
            course=course,
            description=criteria_data["description"],
            defaults={
                "options": criteria_data["options"],
                "review_criteria_type": criteria_data["review_criteria_type"],
            },
        )
        maps.criteria_id_map[criteria_data["id"]] = criteria.id
    print("✓ Review criteria created")


def bulk_create_mapped(model, pending, target_map):
    if not pending:
        return []
    created = model.objects.bulk_create([obj for _, obj in pending])
    for (old_id, _), created_obj in zip(pending, created):
        target_map[old_id] = created_obj.id
    return []


def flush_mapped_batch(model, pending, target_map):
    return bulk_create_mapped(model, pending, target_map)


def build_project_submission(sub_data, project, maps: ImportMaps):
    return ProjectSubmission(
        project=project,
        student_id=maps.user_id_map[sub_data["student_id"]],
        enrollment_id=maps.enrollment_id_map[sub_data["enrollment_id"]],
        github_link=sub_data["github_link"],
        commit_id=sub_data["commit_id"],
        learning_in_public_links=sub_data.get("learning_in_public_links"),
        faq_contribution_url=sub_data.get("faq_contribution_url"),
        time_spent=sub_data.get("time_spent"),
        problems_comments=sub_data.get("problems_comments", ""),
        submitted_at=parse_datetime(sub_data["submitted_at"]),
        project_score=sub_data.get("project_score", 0),
        project_faq_score=sub_data.get("project_faq_score", 0),
        project_learning_in_public_score=sub_data.get(
            "project_learning_in_public_score", 0
        ),
        peer_review_score=sub_data.get("peer_review_score", 0),
        peer_review_learning_in_public_score=sub_data.get(
            "peer_review_learning_in_public_score", 0
        ),
        total_score=sub_data.get("total_score", 0),
        reviewed_enough_peers=sub_data.get("reviewed_enough_peers", False),
        passed=sub_data.get("passed", False),
    )


def create_project_submissions(submissions_data, project, maps: ImportMaps) -> None:
    print(f"Creating {len(submissions_data)} submissions...")
    pending = []
    batch_size = 100

    for sub_data in tqdm(
        submissions_data, desc="Creating submissions", unit="submissions"
    ):
        submission = build_project_submission(sub_data, project, maps)
        pending.append((sub_data["id"], submission))
        if len(pending) >= batch_size:
            pending = flush_mapped_batch(
                ProjectSubmission, pending, maps.submission_id_map
            )

    flush_mapped_batch(ProjectSubmission, pending, maps.submission_id_map)
    print("✓ Submissions created")


def build_peer_review(review_data, maps: ImportMaps):
    return PeerReview(
        submission_under_evaluation_id=maps.submission_id_map[
            review_data["submission_under_evaluation_id"]
        ],
        reviewer_id=maps.submission_id_map[review_data["reviewer_id"]],
        note_to_peer=review_data.get("note_to_peer", ""),
        learning_in_public_links=review_data.get("learning_in_public_links"),
        time_spent_reviewing=review_data.get("time_spent_reviewing"),
        problems_comments=review_data.get("problems_comments", ""),
        optional=review_data.get("optional", False),
        submitted_at=parse_datetime(review_data.get("submitted_at")),
        state=review_data["state"],
    )


def create_peer_reviews(peer_reviews_data, maps: ImportMaps) -> None:
    print(f"Creating {len(peer_reviews_data)} peer reviews...")
    pending = []
    batch_size = 100

    for review_data in tqdm(
        peer_reviews_data, desc="Creating peer reviews", unit="reviews"
    ):
        pending.append((review_data["id"], build_peer_review(review_data, maps)))
        if len(pending) >= batch_size:
            pending = flush_mapped_batch(PeerReview, pending, maps.review_id_map)

    flush_mapped_batch(PeerReview, pending, maps.review_id_map)
    print("✓ Peer reviews created")


def bulk_create_in_batches(model, items, batch_size=100):
    pending = []
    for item in items:
        pending.append(item)
        if len(pending) >= batch_size:
            model.objects.bulk_create(pending)
            pending = []
    if pending:
        model.objects.bulk_create(pending)


def build_criteria_response(response_data, maps: ImportMaps):
    return CriteriaResponse(
        review_id=maps.review_id_map[response_data["review_id"]],
        criteria_id=maps.criteria_id_map[response_data["criteria_id"]],
        answer=response_data.get("answer", ""),
    )


def create_criteria_responses(responses_data, maps: ImportMaps) -> None:
    print(f"Creating {len(responses_data)} criteria responses...")
    records = (
        build_criteria_response(response_data, maps)
        for response_data in tqdm(
            responses_data, desc="Creating responses", unit="responses"
        )
    )
    bulk_create_in_batches(CriteriaResponse, records)
    print("✓ Criteria responses created")


def build_evaluation_score(score_data, maps: ImportMaps):
    return ProjectEvaluationScore(
        submission_id=maps.submission_id_map[score_data["submission_id"]],
        review_criteria_id=maps.criteria_id_map[score_data["review_criteria_id"]],
        score=score_data["score"],
    )


def create_evaluation_scores(scores_data, maps: ImportMaps) -> None:
    print(f"Creating {len(scores_data)} evaluation scores...")
    records = (
        build_evaluation_score(score_data, maps)
        for score_data in tqdm(scores_data, desc="Creating scores", unit="scores")
    )
    bulk_create_in_batches(ProjectEvaluationScore, records)
    print("✓ Evaluation scores created")


def import_project_records(data: ProjectImportData, clear_existing=False):
    maps = ImportMaps()
    course = get_or_create_course(data.course)
    project, should_load = get_or_create_project(
        course, data.project, clear_existing
    )
    if not should_load:
        return project, False

    create_users(data.users, maps)
    create_enrollments(data.enrollments, course, maps)
    create_review_criteria(data.review_criteria, course, maps)
    create_project_submissions(data.submissions, project, maps)
    create_peer_reviews(data.peer_reviews, maps)
    create_criteria_responses(data.criteria_responses, maps)
    create_evaluation_scores(data.evaluation_scores, maps)
    return project, True


def print_success(project) -> None:
    print("\n" + "=" * 80)
    print("✓ Data successfully loaded into local database")
    print("\nYou can now reproduce the scoring bug by running:")
    print("  from courses.projects import score_project")
    print("  from courses.models import Project")
    print(f"  project = Project.objects.get(slug='{project.slug}')")
    print("  score_project(project)")
    print("=" * 80)


def load_project_data(input_file, clear_existing=False):
    """
    Load project data from JSONL file into local database

    Args:
        input_file: Path to JSONL file
        clear_existing: If True, delete existing project data before loading
    """
    data = read_project_import_data(input_file)
    print_import_metadata(data)

    with transaction.atomic():
        project, loaded = import_project_records(data, clear_existing)

    if loaded:
        print_success(project)


def main():
    parser = argparse.ArgumentParser(
        description="Load project data from JSONL file into local database"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to JSONL file"
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing project data before loading"
    )
    
    args = parser.parse_args()
    
    load_project_data(
        input_file=args.file,
        clear_existing=args.clear_existing
    )


if __name__ == "__main__":
    main()
