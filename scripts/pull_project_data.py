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
from datetime import datetime

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    ProjectState,
    PeerReviewState,
)

User = get_user_model()


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
    return {
        "id": enrollment.id,
        "student_id": enrollment.student.id,
        "course_id": enrollment.course.id,
        "enrollment_date": serialize_datetime(enrollment.enrollment_date),
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
    return {
        "id": project.id,
        "course_id": project.course.id,
        "slug": project.slug,
        "title": project.title,
        "description": project.description,
        "submission_due_date": serialize_datetime(project.submission_due_date),
        "learning_in_public_cap_project": project.learning_in_public_cap_project,
        "peer_review_due_date": serialize_datetime(project.peer_review_due_date),
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
    return {
        "id": submission.id,
        "project_id": submission.project.id,
        "student_id": submission.student.id,
        "enrollment_id": submission.enrollment.id,
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "learning_in_public_links": submission.learning_in_public_links,
        "faq_contribution": submission.faq_contribution,
        "time_spent": submission.time_spent,
        "problems_comments": submission.problems_comments,
        "submitted_at": serialize_datetime(submission.submitted_at),
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
    return {
        "id": review.id,
        "submission_under_evaluation_id": review.submission_under_evaluation.id,
        "reviewer_id": review.reviewer.id,
        "note_to_peer": review.note_to_peer,
        "learning_in_public_links": review.learning_in_public_links,
        "time_spent_reviewing": review.time_spent_reviewing,
        "problems_comments": review.problems_comments,
        "optional": review.optional,
        "submitted_at": serialize_datetime(review.submitted_at),
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


def pull_project_data(course_slug, project_slug, output_file=None):
    """
    Pull all data associated with a project
    
    Args:
        course_slug: The course slug (e.g., 'ml-zoomcamp-2025')
        project_slug: The project slug (e.g., 'midterm')
        output_file: Output file path (defaults to data_prod/project_data_{course}_{project}.jsonl)
    """
    
    # Default output file name
    if output_file is None:
        # Create data_prod directory if it doesn't exist
        os.makedirs("data_prod", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"data_prod/project_data_{course_slug}_{project_slug}_{timestamp}.jsonl"
    
    print(f"Pulling data for project: {course_slug}/{project_slug}")
    print(f"Output file: {output_file}")
    print("-" * 80)
    
    # Get the course
    try:
        course = Course.objects.get(slug=course_slug)
        print(f"✓ Found course: {course.title}")
    except Course.DoesNotExist:
        print(f"✗ Course not found: {course_slug}")
        return
    
    # Get the project
    try:
        project = Project.objects.get(course=course, slug=project_slug)
        print(f"✓ Found project: {project.title}")
        print(f"  State: {project.state}")
        print(f"  Points to pass: {project.points_to_pass}")
    except Project.DoesNotExist:
        print(f"✗ Project not found: {project_slug}")
        return
    
    # Get all submissions for this project
    submissions = ProjectSubmission.objects.filter(project=project).select_related(
        'student', 'enrollment'
    )
    print(f"✓ Found {submissions.count()} submissions")
    
    # Get all peer reviews
    peer_reviews = PeerReview.objects.filter(
        submission_under_evaluation__project=project
    ).select_related('submission_under_evaluation', 'reviewer')
    print(f"✓ Found {peer_reviews.count()} peer reviews")
    
    # Get all criteria responses
    criteria_responses = CriteriaResponse.objects.filter(
        review__in=peer_reviews
    ).select_related('review', 'criteria')
    print(f"✓ Found {criteria_responses.count()} criteria responses")
    
    # Get all review criteria for this course
    review_criteria = ReviewCriteria.objects.filter(course=course)
    print(f"✓ Found {review_criteria.count()} review criteria")
    
    # Get all evaluation scores
    evaluation_scores = ProjectEvaluationScore.objects.filter(
        submission__in=submissions
    ).select_related('submission', 'review_criteria')
    print(f"✓ Found {evaluation_scores.count()} evaluation scores")
    
    # Get all enrollments
    enrollments = Enrollment.objects.filter(
        id__in=submissions.values_list('enrollment_id', flat=True)
    ).select_related('student', 'course')
    print(f"✓ Found {enrollments.count()} enrollments")
    
    # Get all users
    user_ids = set(submissions.values_list('student_id', flat=True))
    users = User.objects.filter(id__in=user_ids)
    print(f"✓ Found {users.count()} users")
    
    print("-" * 80)
    print("Writing data to file...")
    
    # Write all data to JSONL file
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write metadata
        f.write(json.dumps({
            "type": "metadata",
            "extracted_at": datetime.now().isoformat(),
            "course_slug": course_slug,
            "project_slug": project_slug,
        }) + '\n')
        
        # Write course
        f.write(json.dumps({
            "type": "course",
            "data": extract_course_data(course)
        }) + '\n')
        
        # Write project
        f.write(json.dumps({
            "type": "project",
            "data": extract_project_data(project)
        }) + '\n')
        
        # Write users
        for user in users:
            f.write(json.dumps({
                "type": "user",
                "data": extract_user_data(user)
            }) + '\n')
        
        # Write enrollments
        for enrollment in enrollments:
            f.write(json.dumps({
                "type": "enrollment",
                "data": extract_enrollment_data(enrollment)
            }) + '\n')
        
        # Write review criteria
        for criteria in review_criteria:
            f.write(json.dumps({
                "type": "review_criteria",
                "data": extract_review_criteria_data(criteria)
            }) + '\n')
        
        # Write submissions
        for submission in submissions:
            f.write(json.dumps({
                "type": "submission",
                "data": extract_submission_data(submission)
            }) + '\n')
        
        # Write peer reviews
        for review in peer_reviews:
            f.write(json.dumps({
                "type": "peer_review",
                "data": extract_peer_review_data(review)
            }) + '\n')
        
        # Write criteria responses
        for response in criteria_responses:
            f.write(json.dumps({
                "type": "criteria_response",
                "data": extract_criteria_response_data(response)
            }) + '\n')
        
        # Write evaluation scores
        for score in evaluation_scores:
            f.write(json.dumps({
                "type": "evaluation_score",
                "data": extract_evaluation_score_data(score)
            }) + '\n')
    
    print(f"✓ Data successfully written to {output_file}")
    print("\nSummary:")
    print("  - 1 course")
    print("  - 1 project")
    print(f"  - {users.count()} users")
    print(f"  - {enrollments.count()} enrollments")
    print(f"  - {review_criteria.count()} review criteria")
    print(f"  - {submissions.count()} submissions")
    print(f"  - {peer_reviews.count()} peer reviews")
    print(f"  - {criteria_responses.count()} criteria responses")
    print(f"  - {evaluation_scores.count()} evaluation scores")


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
