#!/usr/bin/env python
"""
Script to debug project scoring with detailed error checking and logging.

This script runs through the scoring logic step-by-step and catches any
errors that might occur, helping identify production issues.

Usage:
    python scripts/debug_score_project.py --course-slug ml-zoomcamp-2025 --project-slug midterm
"""

import os
import sys
import argparse
import traceback

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from collections import defaultdict
from courses.models import (
    Project,
    ProjectSubmission,
    PeerReview,
    CriteriaResponse,
    ReviewCriteria,
    ProjectEvaluationScore,
)


def debug_score_project(course_slug, project_slug):
    """
    Debug the scoring process with detailed checks
    """
    print("=" * 80)
    print(f"DEBUGGING PROJECT SCORING: {course_slug}/{project_slug}")
    print("=" * 80)
    print()

    try:
        project = Project.objects.get(course__slug=course_slug, slug=project_slug)
        print(f"✓ Found project: {project.title}")
        print(f"  State: {project.state}")
        print(f"  Points to pass: {project.points_to_pass}")
    except Project.DoesNotExist:
        print(f"✗ Project not found: {course_slug}/{project_slug}")
        return
    except Exception as e:
        print(f"✗ Error fetching project: {e}")
        traceback.print_exc()
        return

    print()
    print("-" * 80)
    print("Step 1: Fetching peer reviews")
    print("-" * 80)
    
    try:
        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        )
        print(f"✓ Found {peer_reviews.count()} peer reviews")
        
        submitted_reviews = peer_reviews.filter(state='SU')
        print(f"  - {submitted_reviews.count()} submitted")
        print(f"  - {peer_reviews.count() - submitted_reviews.count()} not submitted")
    except Exception as e:
        print(f"✗ Error fetching peer reviews: {e}")
        traceback.print_exc()
        return

    print()
    print("-" * 80)
    print("Step 2: Fetching criteria responses")
    print("-" * 80)
    
    try:
        criteria_responses = CriteriaResponse.objects.filter(
            review__in=peer_reviews
        )
        print(f"✓ Found {criteria_responses.count()} criteria responses")
        
        # Check for any responses with issues
        responses_with_empty_answer = criteria_responses.filter(answer__isnull=True).count()
        responses_with_empty_answer += criteria_responses.filter(answer='').count()
        print(f"  - {responses_with_empty_answer} responses with empty answers")
    except Exception as e:
        print(f"✗ Error fetching criteria responses: {e}")
        traceback.print_exc()
        return

    print()
    print("-" * 80)
    print("Step 3: Building review dictionaries")
    print("-" * 80)
    
    try:
        responses_by_review = defaultdict(list)
        for response in criteria_responses:
            responses_by_review[response.review_id].append(response)
        
        print(f"✓ Built responses_by_review with {len(responses_by_review)} reviews")
        
        submissions = {}
        reviews_by_submission = {}
        reviews_by_reviewer = {}
        
        for review in peer_reviews:
            submission = review.submission_under_evaluation
            submissions[submission.id] = submission
            
            if submission.id not in reviews_by_submission:
                reviews_by_submission[submission.id] = []
            
            if review.reviewer.id not in reviews_by_reviewer:
                reviews_by_reviewer[review.reviewer.id] = []
            
            if review.state == 'SU':
                reviews_by_submission[submission.id].append(review)
                reviewer = review.reviewer
                reviews_by_reviewer[reviewer.id].append(review)
                review.responses = responses_by_review[review.id]
        
        print(f"✓ Built dictionaries:")
        print(f"  - {len(submissions)} unique submissions")
        print(f"  - {len(reviews_by_submission)} submissions have reviews")
        print(f"  - {len(reviews_by_reviewer)} reviewers")
    except Exception as e:
        print(f"✗ Error building dictionaries: {e}")
        traceback.print_exc()
        return

    print()
    print("-" * 80)
    print("Step 4: Fetching review criteria")
    print("-" * 80)
    
    try:
        criteria = ReviewCriteria.objects.filter(course=project.course).all()
        print(f"✓ Found {criteria.count()} review criteria")
        
        for c in criteria:
            print(f"  - {c.description}: {len(c.options)} options")
    except Exception as e:
        print(f"✗ Error fetching criteria: {e}")
        traceback.print_exc()
        return

    print()
    print("-" * 80)
    print("Step 5: Processing submissions (checking for issues)")
    print("-" * 80)
    
    errors = []
    warnings = []
    
    for i, (submission_id, submission) in enumerate(submissions.items()):
        try:
            reviews = reviews_by_submission.get(submission_id, [])
            
            # THIS IS THE BUG - using submission_id instead of submission.id
            reviewed = reviews_by_reviewer.get(submission_id)
            
            if reviewed is None:
                # Try the correct way
                reviewed_correct = reviews_by_reviewer.get(submission.id)
                
                if reviewed_correct is not None and len(reviewed_correct) > 0:
                    warnings.append(
                        f"Submission {submission_id}: BUG DETECTED! "
                        f"Wrong lookup returned None, correct lookup found {len(reviewed_correct)} reviews"
                    )
            
            # Check for issues with responses
            for review in reviews:
                if not hasattr(review, 'responses'):
                    errors.append(f"Review {review.id} has no responses attribute")
                elif len(review.responses) == 0:
                    warnings.append(f"Review {review.id} has no responses")
                else:
                    for response in review.responses:
                        try:
                            score = response.get_score()
                        except Exception as e:
                            errors.append(
                                f"Review {review.id}, Response {response.id}: "
                                f"Error calculating score: {e}"
                            )
            
            # Progress indicator
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(submissions)} submissions...")
                
        except Exception as e:
            errors.append(f"Submission {submission_id}: {e}")
            traceback.print_exc()
    
    print(f"✓ Processed all {len(submissions)} submissions")
    
    print()
    print("=" * 80)
    print("DIAGNOSIS RESULTS")
    print("=" * 80)
    print()
    
    if errors:
        print(f"❌ ERRORS FOUND ({len(errors)}):")
        for error in errors[:10]:  # Show first 10
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    else:
        print("✓ No errors found")
    
    print()
    
    if warnings:
        print(f"⚠ WARNINGS ({len(warnings)}):")
        for warning in warnings[:10]:  # Show first 10
            print(f"  - {warning}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more warnings")
    else:
        print("✓ No warnings")
    
    print()
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()
    
    if not errors and not warnings:
        print("No issues detected in the scoring logic.")
        print("If production fails, check:")
        print("  1. Database connection timeout/limits")
        print("  2. Memory constraints (large dataset)")
        print("  3. Transaction timeout settings")
        print("  4. Application server timeout")
        print("  5. Check production logs for the actual error message")
    
    if warnings:
        print("The bug at line 286 may not cause immediate failure but")
        print("causes incorrect peer review score calculations.")
        print()
        print("Fix: Change line 286 in courses/projects.py from:")
        print("  reviewed = reviews_by_reviewer.get(submission_id)")
        print("To:")
        print("  reviewed = reviews_by_reviewer.get(submission.id)")
    
    if errors:
        print("Critical errors found that could cause production failures.")
        print("Review the errors above and fix the underlying issues.")
    
    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Debug project scoring to identify production issues"
    )
    parser.add_argument(
        "--course-slug", required=True, help="Course slug (e.g., 'ml-zoomcamp-2025')"
    )
    parser.add_argument(
        "--project-slug", required=True, help="Project slug (e.g., 'midterm')"
    )

    args = parser.parse_args()

    debug_score_project(course_slug=args.course_slug, project_slug=args.project_slug)


if __name__ == "__main__":
    main()
