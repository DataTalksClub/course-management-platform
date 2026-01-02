#!/usr/bin/env python
"""
Script to move/copy review criteria from one course to another.

Usage:
    uv run python scripts/move_criteria.py \\
        --source-course ml-zoomcamp-2024 \\
        --dest-course ml-zoomcamp-2025

    # Preview what would be copied without making changes
    uv run python scripts/move_criteria.py \\
        --source-course ml-zoomcamp-2024 \\
        --dest-course ml-zoomcamp-2025 \\
        --dry-run

    # Move criteria (delete from source after copying)
    uv run python scripts/move_criteria.py \\
        --source-course ml-zoomcamp-2024 \\
        --dest-course ml-zoomcamp-2025 \\
        --delete-in-source
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

from courses.models import Course, ReviewCriteria


def list_criteria(course: Course) -> list[ReviewCriteria]:
    """List all criteria for a course."""
    return list(course.reviewcriteria_set.all().order_by('id'))


def copy_criteria(
    source_course: Course,
    dest_course: Course,
    dry_run: bool = False,
    delete_from_source: bool = False
) -> tuple[list[ReviewCriteria], list[ReviewCriteria]]:
    """
    Copy criteria from source course to destination course.

    Skips criteria that already exist (same description and options).

    Returns a tuple of (created_criteria, deleted_criteria).
    """
    source_criteria = list_criteria(source_course)
    dest_existing = list_criteria(dest_course)

    # Build set of existing (description, type) tuples for quick lookup
    existing_keys = {
        (c.description, c.review_criteria_type)
        for c in dest_existing
    }

    created = []
    to_delete = []

    for criteria in source_criteria:
        key = (criteria.description, criteria.review_criteria_type)
        if key in existing_keys:
            print(f"  ⊘ Skipping existing: {criteria.description}")
            continue

        if dry_run:
            print(f"  + Would create: {criteria.description}")
            created.append(criteria)
            if delete_from_source:
                to_delete.append(criteria)
        else:
            new_criteria = ReviewCriteria.objects.create(
                course=dest_course,
                description=criteria.description,
                options=criteria.options,
                review_criteria_type=criteria.review_criteria_type,
            )
            print(f"  ✓ Created: {new_criteria.description}")
            created.append(new_criteria)
            if delete_from_source:
                to_delete.append(criteria)

    if delete_from_source and to_delete and not dry_run:
        print()
        for criteria in to_delete:
            print(f"  ✗ Deleting from source: {criteria.description}")
            criteria.delete()

    return created, to_delete


def main():
    parser = argparse.ArgumentParser(
        description="Move/copy review criteria from one course to another"
    )
    parser.add_argument(
        "--source-course",
        required=True,
        help="Source course slug"
    )
    parser.add_argument(
        "--dest-course",
        required=True,
        help="Destination course slug"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be copied without making changes"
    )
    parser.add_argument(
        "--delete-in-source",
        action="store_true",
        help="Delete criteria from source course after copying"
    )

    args = parser.parse_args()

    # Get source course
    try:
        source_course = Course.objects.get(slug=args.source_course)
    except Course.DoesNotExist:
        print(f"Error: Source course '{args.source_course}' not found")
        sys.exit(1)

    # Get destination course
    try:
        dest_course = Course.objects.get(slug=args.dest_course)
    except Course.DoesNotExist:
        print(f"Error: Destination course '{args.dest_course}' not found")
        sys.exit(1)

    print("=" * 60)
    print("Criteria Migration")
    print("=" * 60)
    print(f"Source course: {source_course.title} ({source_course.slug})")
    print(f"Destination course: {dest_course.title} ({dest_course.slug})")
    print()

    source_criteria = list_criteria(source_course)
    dest_criteria = list_criteria(dest_course)

    print(f"Source criteria count: {len(source_criteria)}")
    print(f"Destination criteria count: {len(dest_criteria)}")
    print()

    if args.dry_run:
        print("DRY RUN - No changes will be made")
        print()

    print("Migrating criteria:")
    print("-" * 60)

    created, deleted = copy_criteria(
        source_course,
        dest_course,
        dry_run=args.dry_run,
        delete_from_source=args.delete_in_source
    )

    print("-" * 60)
    if args.dry_run:
        print(f"Would create {len(created)} criteria")
        if args.delete_in_source:
            print(f"Would delete {len(deleted)} criteria from source")
    else:
        print(f"Created {len(created)} criteria")
        if args.delete_in_source:
            print(f"Deleted {len(deleted)} criteria from source")

    # Show updated destination criteria
    if not args.dry_run:
        dest_criteria_after = list_criteria(dest_course)
        print(f"Destination course now has {len(dest_criteria_after)} criteria")


if __name__ == "__main__":
    main()
