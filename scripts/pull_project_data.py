#!/usr/bin/env python
"""
Script to pull all data associated with a project from production database.
This extracts all related models to reproduce scoring bugs locally.

Usage:
    python scripts/pull_project_data.py --course-slug ml-zoomcamp-2025 --project-slug midterm
    
The script will create a JSONL file with all the data needed to reproduce the project locally.
"""

import os
import sys
import json
import argparse
from dataclasses import dataclass
from datetime import datetime

# Add parent directory to path so Django can find course_management module
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
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


@dataclass
class ProjectExportData:
    course: Course
    project: Project
    submissions: object
    peer_reviews: object
    criteria_responses: object
    review_criteria: object
    evaluation_scores: object
    enrollments: object
    users: object


@dataclass(frozen=True)
class JsonlCollectionData:
    record_type: str
    items: object
    extractor: object


def serialize_datetime(obj):
    """Helper to serialize datetime objects"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def extract_user_data(user):
    """Extract relevant user data"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "certificate_name": user.certificate_name,
        "dark_mode": user.dark_mode,
    }


def extract_enrollment_data(enrollment):
    """Extract enrollment data"""
    enrollment_date = serialize_datetime(enrollment.enrollment_date)
    return {
        "id": enrollment.id,
        "student_id": enrollment.student.id,
        "course_id": enrollment.course.id,
        "enrollment_date": enrollment_date,
        "display_name": enrollment.display_name,
        "display_on_leaderboard": enrollment.display_on_leaderboard,
        "position_on_leaderboard": enrollment.position_on_leaderboard,
        "certificate_name": enrollment.certificate_name,
        "total_score": enrollment.total_score,
        "certificate_url": enrollment.certificate_url,
        "github_url": enrollment.github_url,
        "linkedin_url": enrollment.linkedin_url,
        "personal_website_url": enrollment.personal_website_url,
        "about_me": enrollment.about_me,
    }


def extract_course_data(course):
    """Extract course data"""
    return {
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "social_media_hashtag": course.social_media_hashtag,
        "first_homework_scored": course.first_homework_scored,
        "finished": course.finished,
        "faq_document_url": course.faq_document_url,
        "min_projects_to_pass": course.min_projects_to_pass,
        "homework_problems_comments_field": course.homework_problems_comments_field,
        "project_passing_score": course.project_passing_score,
        "visible": course.visible,
    }


def extract_project_data(project):
    """Extract project data"""
    submission_due_date = serialize_datetime(project.submission_due_date)
    peer_review_due_date = serialize_datetime(project.peer_review_due_date)
    return {
        "id": project.id,
        "course_id": project.course.id,
        "slug": project.slug,
        "title": project.title,
        "description": project.description,
        "submission_due_date": submission_due_date,
        "learning_in_public_cap_project": project.learning_in_public_cap_project,
        "peer_review_due_date": peer_review_due_date,
        "time_spent_project_field": project.time_spent_project_field,
        "problems_comments_field": project.problems_comments_field,
        "faq_contribution_field": project.faq_contribution_field,
        "learning_in_public_cap_review": project.learning_in_public_cap_review,
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
        "points_for_peer_review": project.points_for_peer_review,
        "time_spent_evaluation_field": project.time_spent_evaluation_field,
        "state": project.state,
        "points_to_pass": project.points_to_pass,
    }


def extract_review_criteria_data(criteria):
    """Extract review criteria data"""
    return {
        "id": criteria.id,
        "course_id": criteria.course.id,
        "description": criteria.description,
        "options": criteria.options,
        "review_criteria_type": criteria.review_criteria_type,
    }


def extract_submission_data(submission):
    """Extract project submission data"""
    submitted_at = serialize_datetime(submission.submitted_at)
    return {
        "id": submission.id,
        "project_id": submission.project.id,
        "student_id": submission.student.id,
        "enrollment_id": submission.enrollment.id,
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "learning_in_public_links": submission.learning_in_public_links,
        "faq_contribution_url": submission.faq_contribution_url,
        "time_spent": submission.time_spent,
        "problems_comments": submission.problems_comments,
        "submitted_at": submitted_at,
        "project_score": submission.project_score,
        "project_faq_score": submission.project_faq_score,
        "project_learning_in_public_score": submission.project_learning_in_public_score,
        "peer_review_score": submission.peer_review_score,
        "peer_review_learning_in_public_score": submission.peer_review_learning_in_public_score,
        "total_score": submission.total_score,
        "reviewed_enough_peers": submission.reviewed_enough_peers,
        "passed": submission.passed,
    }


def extract_peer_review_data(review):
    """Extract peer review data"""
    submitted_at = serialize_datetime(review.submitted_at)
    return {
        "id": review.id,
        "submission_under_evaluation_id": review.submission_under_evaluation.id,
        "reviewer_id": review.reviewer.id,
        "note_to_peer": review.note_to_peer,
        "learning_in_public_links": review.learning_in_public_links,
        "time_spent_reviewing": review.time_spent_reviewing,
        "problems_comments": review.problems_comments,
        "optional": review.optional,
        "submitted_at": submitted_at,
        "state": review.state,
    }


def extract_criteria_response_data(response):
    """Extract criteria response data"""
    return {
        "id": response.id,
        "review_id": response.review.id,
        "criteria_id": response.criteria.id,
        "answer": response.answer,
    }


def extract_evaluation_score_data(score):
    """Extract project evaluation score data"""
    return {
        "id": score.id,
        "submission_id": score.submission.id,
        "review_criteria_id": score.review_criteria.id,
        "score": score.score,
    }


def default_output_file(course_slug, project_slug):
    os.makedirs("data_prod", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        f"data_prod/project_data_{course_slug}_{project_slug}_{timestamp}.jsonl"
    )


def resolve_output_file(course_slug, project_slug, output_file):
    if output_file is None:
        return default_output_file(course_slug, project_slug)
    return output_file


def print_pull_header(course_slug, project_slug, output_file):
    print(f"Pulling data for project: {course_slug}/{project_slug}")
    print(f"Output file: {output_file}")
    print("-" * 80)


def get_course(course_slug):
    try:
        course = Course.objects.get(slug=course_slug)
        print(f"✓ Found course: {course.title}")
        return course
    except Course.DoesNotExist:
        print(f"✗ Course not found: {course_slug}")
        return None


def get_project(course, project_slug):
    try:
        project = Project.objects.get(course=course, slug=project_slug)
        print(f"✓ Found project: {project.title}")
        print(f"  State: {project.state}")
        print(f"  Points to pass: {project.points_to_pass}")
        return project
    except Project.DoesNotExist:
        print(f"✗ Project not found: {project_slug}")
        return None


def project_submissions(project):
    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .select_related("student", "enrollment")
    )
    print(f"✓ Found {submissions.count()} submissions")
    return submissions


def project_peer_reviews(project):
    peer_reviews = PeerReview.objects.filter(
        submission_under_evaluation__project=project
    ).select_related("submission_under_evaluation", "reviewer")
    print(f"✓ Found {peer_reviews.count()} peer reviews")
    return peer_reviews


def project_criteria_responses(peer_reviews):
    criteria_responses = CriteriaResponse.objects.filter(
        review__in=peer_reviews
    ).select_related("review", "criteria")
    print(f"✓ Found {criteria_responses.count()} criteria responses")
    return criteria_responses


def project_review_criteria(course):
    review_criteria = ReviewCriteria.objects.filter(course=course)
    print(f"✓ Found {review_criteria.count()} review criteria")
    return review_criteria


def project_evaluation_scores(submissions):
    evaluation_scores = ProjectEvaluationScore.objects.filter(
        submission__in=submissions
    ).select_related("submission", "review_criteria")
    print(f"✓ Found {evaluation_scores.count()} evaluation scores")
    return evaluation_scores


def project_enrollments(submissions):
    enrollment_ids = submissions.values_list("enrollment_id", flat=True)
    enrollments = Enrollment.objects.filter(
        id__in=enrollment_ids
    ).select_related("student", "course")
    print(f"✓ Found {enrollments.count()} enrollments")
    return enrollments


def project_users(submissions):
    student_ids = submissions.values_list("student_id", flat=True)
    user_ids = set(student_ids)
    users = User.objects.filter(id__in=user_ids)
    print(f"✓ Found {users.count()} users")
    return users


def collect_project_export_data(course, project):
    submissions = project_submissions(project)
    peer_reviews = project_peer_reviews(project)
    criteria_responses = project_criteria_responses(peer_reviews)
    review_criteria = project_review_criteria(course)
    evaluation_scores = project_evaluation_scores(submissions)
    enrollments = project_enrollments(submissions)
    users = project_users(submissions)

    return ProjectExportData(
        course=course,
        project=project,
        submissions=submissions,
        peer_reviews=peer_reviews,
        criteria_responses=criteria_responses,
        review_criteria=review_criteria,
        evaluation_scores=evaluation_scores,
        enrollments=enrollments,
        users=users,
    )


def write_jsonl_record(file, record_type, data):
    file.write(json.dumps({"type": record_type, "data": data}) + "\n")


def write_metadata(file, course_slug, project_slug):
    extracted_at = datetime.now().isoformat()
    file.write(json.dumps({
        "type": "metadata",
        "extracted_at": extracted_at,
        "course_slug": course_slug,
        "project_slug": project_slug,
    }) + "\n")


def write_jsonl_collection(file, record_type, items, extractor):
    for item in items:
        record_data = extractor(item)
        write_jsonl_record(file, record_type, record_data)


def write_project_identity_records(file, export_data):
    course_data = extract_course_data(export_data.course)
    write_jsonl_record(
        file,
        "course",
        course_data,
    )
    project_data = extract_project_data(export_data.project)
    write_jsonl_record(
        file,
        "project",
        project_data,
    )


def project_participant_collections(export_data):
    users = JsonlCollectionData("user", export_data.users, extract_user_data)
    enrollments = JsonlCollectionData(
        "enrollment",
        export_data.enrollments,
        extract_enrollment_data,
    )
    submissions = JsonlCollectionData(
        "submission",
        export_data.submissions,
        extract_submission_data,
    )
    return users, enrollments, submissions


def project_review_collections(export_data):
    review_criteria = JsonlCollectionData(
        "review_criteria",
        export_data.review_criteria,
        extract_review_criteria_data,
    )
    peer_reviews = JsonlCollectionData(
        "peer_review",
        export_data.peer_reviews,
        extract_peer_review_data,
    )
    criteria_responses = JsonlCollectionData(
        "criteria_response",
        export_data.criteria_responses,
        extract_criteria_response_data,
    )
    evaluation_scores = JsonlCollectionData(
        "evaluation_score",
        export_data.evaluation_scores,
        extract_evaluation_score_data,
    )
    return (
        review_criteria,
        peer_reviews,
        criteria_responses,
        evaluation_scores,
    )


def project_related_collections(export_data):
    participant_collections = project_participant_collections(export_data)
    review_collections = project_review_collections(export_data)
    return participant_collections + review_collections


def write_project_related_records(file, export_data):
    collections = project_related_collections(export_data)
    for collection in collections:
        write_jsonl_collection(
            file,
            collection.record_type,
            collection.items,
            collection.extractor,
        )


def write_project_export_file(
    output_file,
    course_slug,
    project_slug,
    export_data,
):
    print("-" * 80)
    print("Writing data to file...")

    with open(output_file, "w", encoding="utf-8") as f:
        write_metadata(f, course_slug, project_slug)
        write_project_identity_records(f, export_data)
        write_project_related_records(f, export_data)


def print_export_summary(output_file, export_data):
    print(f"✓ Data successfully written to {output_file}")
    print("\nSummary:")
    print("  - 1 course")
    print("  - 1 project")
    print(f"  - {export_data.users.count()} users")
    print(f"  - {export_data.enrollments.count()} enrollments")
    print(f"  - {export_data.review_criteria.count()} review criteria")
    print(f"  - {export_data.submissions.count()} submissions")
    print(f"  - {export_data.peer_reviews.count()} peer reviews")
    print(f"  - {export_data.criteria_responses.count()} criteria responses")
    print(f"  - {export_data.evaluation_scores.count()} evaluation scores")


def pull_project_data(course_slug, project_slug, output_file=None):
    """
    Pull all data associated with a project

    Args:
        course_slug: The course slug (e.g., 'ml-zoomcamp-2025')
        project_slug: The project slug (e.g., 'midterm')
        output_file: Output file path (defaults to data_prod/project_data_{course}_{project}.jsonl)
    """
    output_file = resolve_output_file(course_slug, project_slug, output_file)
    print_pull_header(course_slug, project_slug, output_file)

    course = get_course(course_slug)
    if course is None:
        return

    project = get_project(course, project_slug)
    if project is None:
        return

    export_data = collect_project_export_data(course, project)
    write_project_export_file(
        output_file,
        course_slug,
        project_slug,
        export_data,
    )
    print_export_summary(output_file, export_data)


def main():
    parser = argparse.ArgumentParser(
        description="Pull all data associated with a project from production database"
    )
    parser.add_argument(
        "--course-slug",
        required=True,
        help="Course slug (e.g., 'ml-zoomcamp-2025')"
    )
    parser.add_argument(
        "--project-slug",
        required=True,
        help="Project slug (e.g., 'midterm')"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: data_prod/project_data_{course}_{project}_{timestamp}.jsonl)"
    )
    
    args = parser.parse_args()
    
    pull_project_data(
        course_slug=args.course_slug,
        project_slug=args.project_slug,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
