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

from dataclasses import dataclass

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from collections import defaultdict
from courses.models import (
    Project,
    PeerReview,
    CriteriaResponse,
    ReviewCriteria,
)


@dataclass(frozen=True)
class SubmissionDebugData:
    submission_id: int
    submission: object
    reviews_by_submission: dict
    reviews_by_reviewer: dict
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ReviewDictionaryData:
    submissions: dict
    reviews_by_submission: dict
    reviews_by_reviewer: dict


@dataclass(frozen=True)
class SubmissionProcessingData:
    review_data: ReviewDictionaryData
    errors: list[str]
    warnings: list[str]


def print_debug_header(course_slug, project_slug):
    print("=" * 80)
    print(f"DEBUGGING PROJECT SCORING: {course_slug}/{project_slug}")
    print("=" * 80)
    print()


def print_step(title):
    print()
    print("-" * 80)
    print(title)
    print("-" * 80)


def get_project(course_slug, project_slug):
    try:
        project = Project.objects.get(course__slug=course_slug, slug=project_slug)
        print(f"✓ Found project: {project.title}")
        print(f"  State: {project.state}")
        print(f"  Points to pass: {project.points_to_pass}")
        return project
    except Project.DoesNotExist:
        print(f"✗ Project not found: {course_slug}/{project_slug}")
        return None
    except Exception as e:
        print(f"✗ Error fetching project: {e}")
        traceback.print_exc()
        return None


def fetch_peer_reviews(project):
    print_step("Step 1: Fetching peer reviews")
    try:
        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        )
        print(f"✓ Found {peer_reviews.count()} peer reviews")
        
        submitted_reviews = peer_reviews.filter(state='SU')
        print(f"  - {submitted_reviews.count()} submitted")
        print(f"  - {peer_reviews.count() - submitted_reviews.count()} not submitted")
        return peer_reviews
    except Exception as e:
        print(f"✗ Error fetching peer reviews: {e}")
        traceback.print_exc()
        return None


def fetch_criteria_responses(peer_reviews):
    print_step("Step 2: Fetching criteria responses")
    try:
        criteria_responses = CriteriaResponse.objects.filter(
            review__in=peer_reviews
        )
        print(f"✓ Found {criteria_responses.count()} criteria responses")

        # Check for any responses with issues
        responses_with_empty_answer = criteria_responses.filter(
            answer__isnull=True
        ).count()
        responses_with_empty_answer += criteria_responses.filter(answer='').count()
        print(f"  - {responses_with_empty_answer} responses with empty answers")
        return criteria_responses
    except Exception as e:
        print(f"✗ Error fetching criteria responses: {e}")
        traceback.print_exc()
        return None


def responses_by_review(criteria_responses):
    responses = defaultdict(list)
    for response in criteria_responses:
        responses[response.review_id].append(response)
    return responses


def register_review_for_debug(review, response_map, data):
    submission = review.submission_under_evaluation
    data.submissions[submission.id] = submission

    if submission.id not in data.reviews_by_submission:
        data.reviews_by_submission[submission.id] = []

    if review.reviewer.id not in data.reviews_by_reviewer:
        data.reviews_by_reviewer[review.reviewer.id] = []

    if review.state != 'SU':
        return

    data.reviews_by_submission[submission.id].append(review)
    reviewer = review.reviewer
    data.reviews_by_reviewer[reviewer.id].append(review)
    review.responses = response_map[review.id]


def print_review_dictionary_counts(data):
    print("✓ Built dictionaries:")
    print(f"  - {len(data.submissions)} unique submissions")
    print(
        f"  - {len(data.reviews_by_submission)} submissions have reviews"
    )
    print(f"  - {len(data.reviews_by_reviewer)} reviewers")


def build_review_dictionaries(peer_reviews, criteria_responses):
    print_step("Step 3: Building review dictionaries")
    try:
        response_map = responses_by_review(criteria_responses)
        print(f"✓ Built responses_by_review with {len(response_map)} reviews")
        review_data = ReviewDictionaryData(
            submissions={},
            reviews_by_submission={},
            reviews_by_reviewer={},
        )

        for review in peer_reviews:
            register_review_for_debug(review, response_map, review_data)

        print_review_dictionary_counts(review_data)
        return review_data
    except Exception as e:
        print(f"✗ Error building dictionaries: {e}")
        traceback.print_exc()
        return None


def fetch_review_criteria(project):
    print_step("Step 4: Fetching review criteria")
    try:
        criteria = ReviewCriteria.objects.filter(course=project.course).all()
        print(f"✓ Found {criteria.count()} review criteria")

        for c in criteria:
            print(f"  - {c.description}: {len(c.options)} options")
        return criteria
    except Exception as e:
        print(f"✗ Error fetching criteria: {e}")
        traceback.print_exc()
        return None


def check_bug_lookup(submission_id, submission, reviews_by_reviewer, warnings):
    reviewed = reviews_by_reviewer.get(submission_id)
    if reviewed is not None:
        return

    reviewed_correct = reviews_by_reviewer.get(submission.id)
    if reviewed_correct is not None and len(reviewed_correct) > 0:
        warnings.append(
            f"Submission {submission_id}: BUG DETECTED! "
            "Wrong lookup returned None, correct lookup found "
            f"{len(reviewed_correct)} reviews"
        )


def check_review_responses(review, errors, warnings):
    if not hasattr(review, 'responses'):
        errors.append(f"Review {review.id} has no responses attribute")
        return

    if len(review.responses) == 0:
        warnings.append(f"Review {review.id} has no responses")
        return

    responses = review.responses
    for response in responses:
        try:
            response.get_score()
        except Exception as e:
            errors.append(
                f"Review {review.id}, Response {response.id}: "
                f"Error calculating score: {e}"
            )


def process_submission(
    data: SubmissionDebugData,
):
    reviews = data.reviews_by_submission.get(data.submission_id, [])
    check_bug_lookup(
        data.submission_id,
        data.submission,
        data.reviews_by_reviewer,
        data.warnings,
    )

    for review in reviews:
        check_review_responses(review, data.errors, data.warnings)


def submission_debug_data(data, submission_id, submission):
    return SubmissionDebugData(
        submission_id=submission_id,
        submission=submission,
        reviews_by_submission=data.review_data.reviews_by_submission,
        reviews_by_reviewer=data.review_data.reviews_by_reviewer,
        errors=data.errors,
        warnings=data.warnings,
    )


def print_submission_progress(processed_count, total_count):
    if processed_count % 50 != 0:
        return
    print(
        f"  Processed {processed_count}/"
        f"{total_count} submissions..."
    )


def process_submission_item(data, index, item):
    submission_id, submission = item
    try:
        debug_data = submission_debug_data(data, submission_id, submission)
        process_submission(debug_data)
        processed_count = index + 1
        total_count = len(data.review_data.submissions)
        print_submission_progress(processed_count, total_count)
    except Exception as e:
        data.errors.append(f"Submission {submission_id}: {e}")
        traceback.print_exc()


def process_submissions(review_data):
    print_step("Step 5: Processing submissions (checking for issues)")
    errors = []
    warnings = []
    processing_data = SubmissionProcessingData(
        review_data=review_data,
        errors=errors,
        warnings=warnings,
    )

    for index, item in enumerate(review_data.submissions.items()):
        process_submission_item(processing_data, index, item)

    print(f"✓ Processed all {len(review_data.submissions)} submissions")
    return errors, warnings


def print_limited_findings(label, findings, empty_message):
    if findings:
        print(f"{label} ({len(findings)}):")
        limited_findings = findings[:10]
        for finding in limited_findings:
            print(f"  - {finding}")
        if len(findings) > 10:
            print(f"  ... and {len(findings) - 10} more")
    else:
        print(empty_message)


def print_diagnosis(errors, warnings):
    print()
    print("=" * 80)
    print("DIAGNOSIS RESULTS")
    print("=" * 80)
    print()
    print_limited_findings("❌ ERRORS FOUND", errors, "✓ No errors found")
    print()
    print_limited_findings("⚠ WARNINGS", warnings, "✓ No warnings")


def print_no_issue_recommendations():
    print("No issues detected in the scoring logic.")
    print("If production fails, check:")
    print("  1. Database connection timeout/limits")
    print("  2. Memory constraints (large dataset)")
    print("  3. Transaction timeout settings")
    print("  4. Application server timeout")
    print("  5. Check production logs for the actual error message")


def print_warning_recommendations():
    print("The bug at line 286 may not cause immediate failure but")
    print("causes incorrect peer review score calculations.")
    print()
    print("Fix: Change line 286 in courses/projects.py from:")
    print("  reviewed = reviews_by_reviewer.get(submission_id)")
    print("To:")
    print("  reviewed = reviews_by_reviewer.get(submission.id)")


def print_recommendations(errors, warnings):
    print()
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()

    if not errors and not warnings:
        print_no_issue_recommendations()

    if warnings:
        print_warning_recommendations()

    if errors:
        print("Critical errors found that could cause production failures.")
        print("Review the errors above and fix the underlying issues.")

    print()
    print("=" * 80)


def debug_score_project(course_slug, project_slug):
    """
    Debug the scoring process with detailed checks
    """
    print_debug_header(course_slug, project_slug)

    project = get_project(course_slug, project_slug)
    if project is None:
        return

    peer_reviews = fetch_peer_reviews(project)
    if peer_reviews is None:
        return

    criteria_responses = fetch_criteria_responses(peer_reviews)
    if criteria_responses is None:
        return

    review_data = build_review_dictionaries(peer_reviews, criteria_responses)
    if review_data is None:
        return

    if fetch_review_criteria(project) is None:
        return

    errors, warnings = process_submissions(review_data)
    print_diagnosis(errors, warnings)
    print_recommendations(errors, warnings)


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
