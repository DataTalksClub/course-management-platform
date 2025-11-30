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
from datetime import datetime
from collections import defaultdict
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


def load_project_data(input_file, clear_existing=False):
    """
    Load project data from JSONL file into local database
    
    Args:
        input_file: Path to JSONL file
        clear_existing: If True, delete existing project data before loading
    """
    
    print(f"Loading data from: {input_file}")
    print("-" * 80)
    
    # Read all data
    data = {
        "metadata": None,
        "course": None,
        "project": None,
        "users": [],
        "enrollments": [],
        "review_criteria": [],
        "submissions": [],
        "peer_reviews": [],
        "criteria_responses": [],
        "evaluation_scores": [],
    }
    
    # Count total lines for progress bar
    with open(input_file, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, total=total_lines, desc="Reading data", unit="records"):
            record = json.loads(line)
            record_type = record["type"]
            
            if record_type == "metadata":
                data["metadata"] = record
            elif record_type == "course":
                data["course"] = record["data"]
            elif record_type == "project":
                data["project"] = record["data"]
            elif record_type == "user":
                data["users"].append(record["data"])
            elif record_type == "enrollment":
                data["enrollments"].append(record["data"])
            elif record_type == "review_criteria":
                data["review_criteria"].append(record["data"])
            elif record_type == "submission":
                data["submissions"].append(record["data"])
            elif record_type == "peer_review":
                data["peer_reviews"].append(record["data"])
            elif record_type == "criteria_response":
                data["criteria_responses"].append(record["data"])
            elif record_type == "evaluation_score":
                data["evaluation_scores"].append(record["data"])
    
    print(f"✓ Read data from file")
    print(f"  Extracted at: {data['metadata']['extracted_at']}")
    print(f"  Course: {data['metadata']['course_slug']}")
    print(f"  Project: {data['metadata']['project_slug']}")
    print()
    
    # ID mappings (old_id -> new_id)
    user_id_map = {}
    enrollment_id_map = {}
    criteria_id_map = {}
    submission_id_map = {}
    review_id_map = {}
    
    with transaction.atomic():
        # Check if course exists or create it
        course_data = data["course"]
        course, created = Course.objects.get_or_create(
            slug=course_data["slug"],
            defaults={
                "title": course_data["title"],
                "description": course_data["description"],
                "social_media_hashtag": course_data.get("social_media_hashtag", ""),
                "first_homework_scored": course_data.get("first_homework_scored", False),
                "finished": course_data.get("finished", False),
                "faq_document_url": course_data.get("faq_document_url", ""),
                "min_projects_to_pass": course_data.get("min_projects_to_pass", 1),
                "homework_problems_comments_field": course_data.get("homework_problems_comments_field", False),
                "project_passing_score": course_data.get("project_passing_score", 0),
                "visible": course_data.get("visible", True),
            }
        )
        
        if created:
            print(f"✓ Created course: {course.title}")
        else:
            print(f"✓ Course already exists: {course.title}")
        
        # Check if project exists
        project_data = data["project"]
        project, created = Project.objects.get_or_create(
            course=course,
            slug=project_data["slug"],
            defaults={
                "title": project_data["title"],
                "description": project_data["description"],
                "submission_due_date": parse_datetime(project_data["submission_due_date"]),
                "learning_in_public_cap_project": project_data.get("learning_in_public_cap_project", 14),
                "peer_review_due_date": parse_datetime(project_data["peer_review_due_date"]),
                "time_spent_project_field": project_data.get("time_spent_project_field", True),
                "problems_comments_field": project_data.get("problems_comments_field", True),
                "faq_contribution_field": project_data.get("faq_contribution_field", True),
                "learning_in_public_cap_review": project_data.get("learning_in_public_cap_review", 2),
                "number_of_peers_to_evaluate": project_data.get("number_of_peers_to_evaluate", 3),
                "points_for_peer_review": project_data.get("points_for_peer_review", 3),
                "time_spent_evaluation_field": project_data.get("time_spent_evaluation_field", True),
                "state": project_data["state"],
            }
        )
        
        if created:
            print(f"✓ Created project: {project.title}")
        else:
            print(f"⚠ Project already exists: {project.title}")
            if clear_existing:
                print("  Clearing existing project data...")
                ProjectEvaluationScore.objects.filter(submission__project=project).delete()
                CriteriaResponse.objects.filter(review__submission_under_evaluation__project=project).delete()
                PeerReview.objects.filter(submission_under_evaluation__project=project).delete()
                ProjectSubmission.objects.filter(project=project).delete()
                print("  ✓ Cleared")
            else:
                print("  Use --clear-existing to replace data")
                return
        
        # Create users
        print(f"\nCreating {len(data['users'])} users...")
        
        # Get all existing usernames in one query
        existing_usernames = {u.username: u for u in User.objects.filter(
            username__in=[user_data["username"] for user_data in data["users"]]
        )}
        
        users_to_create = []
        for user_data in tqdm(data["users"], desc="Processing users", unit="users"):
            old_id = user_data["id"]
            username = user_data["username"]
            
            if username in existing_usernames:
                user_id_map[old_id] = existing_usernames[username].id
            else:
                user = User(
                    username=username,
                    email=user_data["email"],
                    certificate_name=user_data.get("certificate_name", ""),
                    dark_mode=user_data.get("dark_mode", False),
                )
                users_to_create.append((old_id, user))
        
        # Bulk create new users
        if users_to_create:
            created_users = User.objects.bulk_create([u for _, u in users_to_create])
            for (old_id, _), created_user in zip(users_to_create, created_users):
                user_id_map[old_id] = created_user.id
        
        print(f"✓ Users ready ({len(users_to_create)} created, {len(existing_usernames)} existing)")
        
        # Create enrollments
        print(f"Creating {len(data['enrollments'])} enrollments...")
        
        # Get all existing enrollments for this course in one query
        existing_enrollments = {e.student_id: e for e in Enrollment.objects.filter(
            course=course,
            student_id__in=list(user_id_map.values())
        )}
        
        enrollments_to_create = []
        for enroll_data in tqdm(data["enrollments"], desc="Processing enrollments", unit="enrollments"):
            old_id = enroll_data["id"]
            old_student_id = enroll_data["student_id"]
            new_student_id = user_id_map[old_student_id]
            
            if new_student_id in existing_enrollments:
                enrollment_id_map[old_id] = existing_enrollments[new_student_id].id
            else:
                enrollment = Enrollment(
                    student_id=new_student_id,
                    course=course,
                    enrollment_date=parse_datetime(enroll_data["enrollment_date"]),
                    display_name=enroll_data.get("display_name", ""),
                    display_on_leaderboard=enroll_data.get("display_on_leaderboard", True),
                    position_on_leaderboard=enroll_data.get("position_on_leaderboard"),
                    certificate_name=enroll_data.get("certificate_name"),
                    total_score=enroll_data.get("total_score", 0),
                    certificate_url=enroll_data.get("certificate_url"),
                    github_url=enroll_data.get("github_url"),
                    linkedin_url=enroll_data.get("linkedin_url"),
                    personal_website_url=enroll_data.get("personal_website_url"),
                    about_me=enroll_data.get("about_me"),
                )
                enrollments_to_create.append((old_id, enrollment))
        
        # Bulk create new enrollments
        if enrollments_to_create:
            created_enrollments = Enrollment.objects.bulk_create([e for _, e in enrollments_to_create])
            for (old_id, _), created_enrollment in zip(enrollments_to_create, created_enrollments):
                enrollment_id_map[old_id] = created_enrollment.id
        
        print(f"✓ Enrollments ready ({len(enrollments_to_create)} created, {len(existing_enrollments)} existing)")
        
        # Create review criteria
        print(f"Creating {len(data['review_criteria'])} review criteria...")
        for criteria_data in data["review_criteria"]:
            old_id = criteria_data["id"]
            
            criteria, created = ReviewCriteria.objects.get_or_create(
                course=course,
                description=criteria_data["description"],
                defaults={
                    "options": criteria_data["options"],
                    "review_criteria_type": criteria_data["review_criteria_type"],
                }
            )
            criteria_id_map[old_id] = criteria.id
        print(f"✓ Review criteria created")
        
        # Create submissions
        print(f"Creating {len(data['submissions'])} submissions...")
        submissions_to_create = []
        batch_size = 100
        
        for sub_data in tqdm(data["submissions"], desc="Creating submissions", unit="submissions"):
            old_id = sub_data["id"]
            old_student_id = sub_data["student_id"]
            old_enrollment_id = sub_data["enrollment_id"]
            
            submission = ProjectSubmission(
                project=project,
                student_id=user_id_map[old_student_id],
                enrollment_id=enrollment_id_map[old_enrollment_id],
                github_link=sub_data["github_link"],
                commit_id=sub_data["commit_id"],
                learning_in_public_links=sub_data.get("learning_in_public_links"),
                faq_contribution=sub_data.get("faq_contribution", ""),
                time_spent=sub_data.get("time_spent"),
                problems_comments=sub_data.get("problems_comments", ""),
                submitted_at=parse_datetime(sub_data["submitted_at"]),
                project_score=sub_data.get("project_score", 0),
                project_faq_score=sub_data.get("project_faq_score", 0),
                project_learning_in_public_score=sub_data.get("project_learning_in_public_score", 0),
                peer_review_score=sub_data.get("peer_review_score", 0),
                peer_review_learning_in_public_score=sub_data.get("peer_review_learning_in_public_score", 0),
                total_score=sub_data.get("total_score", 0),
                reviewed_enough_peers=sub_data.get("reviewed_enough_peers", False),
                passed=sub_data.get("passed", False),
            )
            submissions_to_create.append((old_id, submission))
            
            if len(submissions_to_create) >= batch_size:
                created = ProjectSubmission.objects.bulk_create([s for _, s in submissions_to_create])
                for (old_id, _), created_sub in zip(submissions_to_create, created):
                    submission_id_map[old_id] = created_sub.id
                submissions_to_create = []
        
        # Insert remaining
        if submissions_to_create:
            created = ProjectSubmission.objects.bulk_create([s for _, s in submissions_to_create])
            for (old_id, _), created_sub in zip(submissions_to_create, created):
                submission_id_map[old_id] = created_sub.id
        
        print("✓ Submissions created")
        
        # Create peer reviews
        print(f"Creating {len(data['peer_reviews'])} peer reviews...")
        reviews_to_create = []
        
        for review_data in tqdm(data["peer_reviews"], desc="Creating peer reviews", unit="reviews"):
            old_id = review_data["id"]
            old_submission_id = review_data["submission_under_evaluation_id"]
            old_reviewer_id = review_data["reviewer_id"]
            
            review = PeerReview(
                submission_under_evaluation_id=submission_id_map[old_submission_id],
                reviewer_id=submission_id_map[old_reviewer_id],
                note_to_peer=review_data.get("note_to_peer", ""),
                learning_in_public_links=review_data.get("learning_in_public_links"),
                time_spent_reviewing=review_data.get("time_spent_reviewing"),
                problems_comments=review_data.get("problems_comments", ""),
                optional=review_data.get("optional", False),
                submitted_at=parse_datetime(review_data.get("submitted_at")),
                state=review_data["state"],
            )
            reviews_to_create.append((old_id, review))
            
            if len(reviews_to_create) >= batch_size:
                created = PeerReview.objects.bulk_create([r for _, r in reviews_to_create])
                for (old_id, _), created_review in zip(reviews_to_create, created):
                    review_id_map[old_id] = created_review.id
                reviews_to_create = []
        
        # Insert remaining
        if reviews_to_create:
            created = PeerReview.objects.bulk_create([r for _, r in reviews_to_create])
            for (old_id, _), created_review in zip(reviews_to_create, created):
                review_id_map[old_id] = created_review.id
        
        print("✓ Peer reviews created")
        
        # Create criteria responses
        print(f"Creating {len(data['criteria_responses'])} criteria responses...")
        responses_to_create = []
        
        for response_data in tqdm(data["criteria_responses"], desc="Creating responses", unit="responses"):
            old_review_id = response_data["review_id"]
            old_criteria_id = response_data["criteria_id"]
            
            response = CriteriaResponse(
                review_id=review_id_map[old_review_id],
                criteria_id=criteria_id_map[old_criteria_id],
                answer=response_data.get("answer", ""),
            )
            responses_to_create.append(response)
            
            if len(responses_to_create) >= batch_size:
                CriteriaResponse.objects.bulk_create(responses_to_create)
                responses_to_create = []
        
        # Insert remaining
        if responses_to_create:
            CriteriaResponse.objects.bulk_create(responses_to_create)
        
        print("✓ Criteria responses created")
        
        # Create evaluation scores
        print(f"Creating {len(data['evaluation_scores'])} evaluation scores...")
        scores_to_create = []
        
        for score_data in tqdm(data["evaluation_scores"], desc="Creating scores", unit="scores"):
            old_submission_id = score_data["submission_id"]
            old_criteria_id = score_data["review_criteria_id"]
            
            score = ProjectEvaluationScore(
                submission_id=submission_id_map[old_submission_id],
                review_criteria_id=criteria_id_map[old_criteria_id],
                score=score_data["score"],
            )
            scores_to_create.append(score)
            
            if len(scores_to_create) >= batch_size:
                ProjectEvaluationScore.objects.bulk_create(scores_to_create)
                scores_to_create = []
        
        # Insert remaining
        if scores_to_create:
            ProjectEvaluationScore.objects.bulk_create(scores_to_create)
        
        print("✓ Evaluation scores created")
    
    print("\n" + "=" * 80)
    print("✓ Data successfully loaded into local database")
    print("\nYou can now reproduce the scoring bug by running:")
    print("  from courses.projects import score_project")
    print("  from courses.models import Project")
    print(f"  project = Project.objects.get(slug='{project.slug}')")
    print("  score_project(project)")
    print("=" * 80)


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
