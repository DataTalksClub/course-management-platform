#!/usr/bin/env python
"""
Script to score a project and display the results.

This script runs the score_project() function on a specified project
and displays detailed results including any scoring issues.

Usage:
    python scripts/score_project.py --course-slug ml-zoomcamp-2025 --project-slug midterm
"""

import os
import sys
import argparse

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django

django.setup()

from courses.models import Project, ProjectSubmission
from courses.projects import score_project


def score_and_display(course_slug, project_slug):
    """
    Score a project and display detailed results
    """
    try:
        project = Project.objects.get(course__slug=course_slug, slug=project_slug)
    except Project.DoesNotExist:
        print(f"✗ Project not found: {course_slug}/{project_slug}")
        return

    print("=" * 80)
    print(f"SCORING PROJECT: {project.course.slug}/{project.slug}")
    print("=" * 80)
    print()

    print(f"Project: {project.title}")
    print(f"State: {project.state}")
    print(f"Points to pass: {project.points_to_pass}")
    print(f"Number of peers to evaluate: {project.number_of_peers_to_evaluate}")
    print(f"Points for peer review: {project.points_for_peer_review}")
    print()

    # Count submissions before scoring
    submissions = ProjectSubmission.objects.filter(project=project)
    print(f"Total submissions: {submissions.count()}")
    print()

    # Run scoring
    print("Running score_project()...")
    print("-" * 80)
    status, message = score_project(project)
    print("-" * 80)
    print()

    print(f"Status: {status.value}")
    print(f"Message: {message}")
    print()

    # Display results
    submissions = ProjectSubmission.objects.filter(project=project).order_by("-total_score")

    print("=" * 80)
    print("SCORING RESULTS")
    print("=" * 80)
    print()

    passed_count = submissions.filter(passed=True).count()
    print(f"Passed: {passed_count}/{submissions.count()}")
    print()

    print("Top 10 submissions:")
    print()
    print(
        f"{'ID':<6} {'Proj':>5} {'FAQ':>4} {'LIP':>4} {'PeerRev':>8} {'PeerLIP':>8} {'Total':>6} {'RevEnough':>10} {'Passed':>7}"
    )
    print("-" * 80)

    for sub in submissions[:10]:
        print(
            f"{sub.id:<6} {sub.project_score:>5} {sub.project_faq_score:>4} "
            f"{sub.project_learning_in_public_score:>4} {sub.peer_review_score:>8} "
            f"{sub.peer_review_learning_in_public_score:>8} {sub.total_score:>6} "
            f"{'Yes' if sub.reviewed_enough_peers else 'No':>10} "
            f"{'Yes' if sub.passed else 'No':>7}"
        )

    if submissions.count() > 10:
        print(f"\n... and {submissions.count() - 10} more submissions")

    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Score a project and display results")
    parser.add_argument(
        "--course-slug", required=True, help="Course slug (e.g., 'ml-zoomcamp-2025')"
    )
    parser.add_argument(
        "--project-slug", required=True, help="Project slug (e.g., 'midterm')"
    )

    args = parser.parse_args()

    score_and_display(course_slug=args.course_slug, project_slug=args.project_slug)


if __name__ == "__main__":
    main()
