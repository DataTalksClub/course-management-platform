#!/usr/bin/env python
"""
Script to demonstrate and verify the bug in project scoring.

This script shows the specific line where the bug occurs and explains
the impact on scoring.
"""

import os
import sys
import django
from collections import defaultdict
from pathlib import Path

# Add parent directory to path so Django can find course_management module.
project_root = Path(__file__).resolve().parent.parent
project_root_path = str(project_root)
sys.path.insert(0, project_root_path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")
django.setup()

from courses.models import Project, ProjectSubmission, PeerReview


def get_project(course_slug, project_slug):
    try:
        return Project.objects.get(
            course__slug=course_slug,
            slug=project_slug
        )
    except Project.DoesNotExist:
        print(f"Project not found: {course_slug}/{project_slug}")
        print("Please run pull_project_data.py and load_project_data.py first")
        return None


def print_bug_header(project):
    print("=" * 80)
    print(f"BUG ANALYSIS: {project.course.slug}/{project.slug}")
    print("=" * 80)
    print()


def print_bug_location():
    print("BUG LOCATION:")
    print("  File: courses/projects.py")
    print("  Function: score_project()")
    print("  Line: 286")
    print()

    print("BUGGY CODE:")
    print("  reviewed = reviews_by_reviewer.get(submission_id)")
    print()

    print("CORRECT CODE:")
    print("  reviewed = reviews_by_reviewer.get(submission.id)")
    print()


def print_bug_explanation():
    print("EXPLANATION:")
    print("  The bug occurs in the loop that processes each submission.")
    print("  At line 284: for submission_id, submission in submissions.items():")
    print("  - submission_id: ID of the submission being scored/evaluated")
    print("  - submission: The submission object being evaluated")
    print()
    print("  The code builds two dictionaries:")
    print("  - reviews_by_submission[sub_id]: reviews WHERE sub_id is being evaluated")
    print("  - reviews_by_reviewer[sub_id]: reviews WHERE sub_id is the reviewer")
    print()
    print("  At line 286, we want to find reviews written BY this submission")
    print("  (i.e., where this submission is the reviewer).")
    print()
    print("  WRONG: reviews_by_reviewer.get(submission_id)")
    print("         This looks up reviews by the ID of the submission being evaluated")
    print()
    print("  RIGHT: reviews_by_reviewer.get(submission.id)")
    print("         This looks up reviews by the submission's own ID")
    print()
    print("  Since submission_id == submission.id in the items() loop, you might")
    print("  think they're the same, but the bug manifests because of the logic")
    print("  flow and how the variables are used in context.")
    print()


def print_bug_details(project):
    print_bug_header(project)
    print_bug_location()
    print_bug_explanation()


def project_reviews(project):
    return PeerReview.objects.filter(
        submission_under_evaluation__project=project
    )


def review_counts_by_reviewer(submitted_reviews):
    reviews_by_reviewer = defaultdict(int)
    for review in submitted_reviews:
        reviews_by_reviewer[review.reviewer.id] += 1
    return reviews_by_reviewer


def print_submission_review_completion(project, submissions, submitted_reviews):
    reviews_by_reviewer = review_counts_by_reviewer(submitted_reviews)

    print("  Review completion by students:")
    ordered_submissions = submissions.order_by('id')
    limited_submissions = ordered_submissions[:10]
    for sub in limited_submissions:
        count = reviews_by_reviewer.get(sub.id, 0)
        expected = project.number_of_peers_to_evaluate
        status = "✓" if count >= expected else "✗"
        print(f"    {status} Submission {sub.id}: {count}/{expected} reviews completed")

    submission_count = submissions.count()
    if submission_count > 10:
        remaining_count = submission_count - 10
        print(f"    ... and {remaining_count} more")


def print_project_impact(project):
    submissions = ProjectSubmission.objects.filter(project=project)
    peer_reviews = project_reviews(project)

    print("IMPACT ON THIS PROJECT:")
    submission_count = submissions.count()
    peer_review_count = peer_reviews.count()
    print(f"  Total submissions: {submission_count}")
    print(f"  Total peer reviews: {peer_review_count}")
    print(f"  Expected reviews per person: {project.number_of_peers_to_evaluate}")
    print()

    submitted_reviews = peer_reviews.filter(state='SU')
    print(f"  Submitted reviews: {submitted_reviews.count()}")
    print()

    print_submission_review_completion(project, submissions, submitted_reviews)
    print()


def print_fix_footer():
    print("To fix this bug, change line 286 in courses/projects.py")
    print("=" * 80)


def analyze_scoring_bug(course_slug, project_slug):
    """
    Analyze the scoring bug for a specific project
    """
    project = get_project(course_slug, project_slug)
    if project is None:
        return

    print_bug_details(project)
    print_project_impact(project)
    print_fix_footer()


def parse_args(argv):
    if len(argv) == 3:
        return argv[1], argv[2]

    course_slug = "ml-zoomcamp-2025"
    project_slug = "midterm"
    print(f"Usage: python {argv[0]} <course-slug> <project-slug>")
    print(f"Using default: {course_slug}/{project_slug}")
    print()
    return course_slug, project_slug


def main(argv=None):
    argv = argv or sys.argv
    course_slug, project_slug = parse_args(argv)
    analyze_scoring_bug(course_slug, project_slug)


if __name__ == "__main__":
    main()
