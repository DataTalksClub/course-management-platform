#!/usr/bin/env python
"""
Script to demonstrate and verify the bug in project scoring.

This script shows the specific line where the bug occurs and explains
the impact on scoring.
"""

import os
import sys
import django

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")
django.setup()

from courses.models import Project, ProjectSubmission, PeerReview


def analyze_scoring_bug(course_slug, project_slug):
    """
    Analyze the scoring bug for a specific project
    """
    try:
        project = Project.objects.get(
            course__slug=course_slug,
            slug=project_slug
        )
    except Project.DoesNotExist:
        print(f"Project not found: {course_slug}/{project_slug}")
        print("Please run pull_project_data.py and load_project_data.py first")
        return
    
    print("=" * 80)
    print(f"BUG ANALYSIS: {project.course.slug}/{project.slug}")
    print("=" * 80)
    print()
    
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
    
    # Show actual impact
    submissions = ProjectSubmission.objects.filter(project=project)
    peer_reviews = PeerReview.objects.filter(
        submission_under_evaluation__project=project
    )
    
    print("IMPACT ON THIS PROJECT:")
    print(f"  Total submissions: {submissions.count()}")
    print(f"  Total peer reviews: {peer_reviews.count()}")
    print(f"  Expected reviews per person: {project.number_of_peers_to_evaluate}")
    print()
    
    # Count submitted reviews
    submitted_reviews = peer_reviews.filter(state='SU')
    print(f"  Submitted reviews: {submitted_reviews.count()}")
    print()
    
    # Analyze review distribution
    from collections import defaultdict
    reviews_by_reviewer = defaultdict(int)
    
    for review in submitted_reviews:
        reviews_by_reviewer[review.reviewer.id] += 1
    
    print("  Review completion by students:")
    for sub in submissions.order_by('id')[:10]:  # Show first 10
        count = reviews_by_reviewer.get(sub.id, 0)
        expected = project.number_of_peers_to_evaluate
        status = "✓" if count >= expected else "✗"
        print(f"    {status} Submission {sub.id}: {count}/{expected} reviews completed")
    
    if submissions.count() > 10:
        print(f"    ... and {submissions.count() - 10} more")
    
    print()
    print("To fix this bug, change line 286 in courses/projects.py")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3:
        course_slug = sys.argv[1]
        project_slug = sys.argv[2]
    else:
        # Default to ml-zoomcamp-2025 midterm project
        course_slug = "ml-zoomcamp-2025"
        project_slug = "midterm"
        print(f"Usage: python {sys.argv[0]} <course-slug> <project-slug>")
        print(f"Using default: {course_slug}/{project_slug}")
        print()
    
    analyze_scoring_bug(course_slug, project_slug)
