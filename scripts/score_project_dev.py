#!/usr/bin/env python
"""
Script to score a project on dev environment via SSH tunnel.

Prerequisites:
1. Open SSH tunnel: ssh bastion-tunnel
2. .envrc file with DB_PASSWORD and DJANGO_SECRET

Usage:
    python scripts/score_project_dev.py --course-slug ml-zoomcamp-2025 --project-slug midterm
"""

import os
import sys
import argparse
import time
import re

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Parse .envrc file
envrc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.envrc')
env_vars = {}

if os.path.exists(envrc_path):
    with open(envrc_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('export '):
                # Parse export VAR='value' or export VAR="value"
                match = re.match(r"export\s+(\w+)=['\"](.+)['\"]", line)
                if match:
                    key, value = match.groups()
                    env_vars[key] = value

# Set environment variables
if 'DB_PASSWORD' in env_vars:
    os.environ['DATABASE_URL'] = f"postgresql://pgusr:{env_vars['DB_PASSWORD']}@localhost:5433/dev"
    print(f"✓ Loaded DB_PASSWORD from .envrc")
else:
    print("ERROR: DB_PASSWORD not found in .envrc")
    sys.exit(1)

if 'DJANGO_SECRET' in env_vars:
    os.environ['SECRET_KEY'] = env_vars['DJANGO_SECRET']
    print(f"✓ Loaded DJANGO_SECRET from .envrc")
else:
    print("ERROR: DJANGO_SECRET not found in .envrc")
    sys.exit(1)

print(f"✓ DATABASE_URL: {os.environ['DATABASE_URL']}")
print()

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from courses.models import Project, ProjectSubmission
from courses.projects import score_project


def score_and_display(course_slug, project_slug):
    """
    Score a project and display detailed results with timing
    """
    try:
        project = Project.objects.get(course__slug=course_slug, slug=project_slug)
    except Project.DoesNotExist:
        print(f"✗ Project not found: {course_slug}/{project_slug}")
        return

    print("=" * 80)
    print(f"SCORING PROJECT (DEV): {project.course.slug}/{project.slug}")
    print("=" * 80)
    print()

    print(f"Project: {project.title}")
    print(f"State: {project.state}")
    print(f"Points to pass: {project.points_to_pass}")
    print(f"Number of peers to evaluate: {project.number_of_peers_to_evaluate}")
    print(f"Points for peer review: {project.points_for_peer_review}")
    print()

    if project.state != "PR":
        print(f"⚠ WARNING: Project state is '{project.state}', should be 'PR' (PEER_REVIEWING)")
        print("  Update the state manually in the database first:")
        print(f"  UPDATE courses_project SET state='PR' WHERE id={project.id};")
        print()
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return

    # Count submissions before scoring
    submissions = ProjectSubmission.objects.filter(project=project)
    print(f"Total submissions: {submissions.count()}")
    print()

    # Run scoring with timing
    print("Running score_project()...")
    print("-" * 80)
    
    start_time = time.time()
    status, message = score_project(project)
    end_time = time.time()
    
    print("-" * 80)
    print()

    print(f"Status: {status.value}")
    print(f"Message: {message}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
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
    parser = argparse.ArgumentParser(description="Score a project on dev environment")
    parser.add_argument(
        "--course-slug", required=True, help="Course slug (e.g., 'ml-zoomcamp-2025')"
    )
    parser.add_argument(
        "--project-slug", required=True, help="Project slug (e.g., 'midterm')"
    )

    args = parser.parse_args()

    print("Connecting to dev database via SSH tunnel...")
    print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
    print()

    score_and_display(course_slug=args.course_slug, project_slug=args.project_slug)


if __name__ == "__main__":
    main()
