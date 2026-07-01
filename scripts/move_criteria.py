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
from dataclasses import dataclass
from pathlib import Path

# Add parent directory to path so Django can find course_management module.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")

import django
django.setup()

from courses.models import Course, ReviewCriteria


@dataclass(frozen=True)
class CriteriaCopyData:
    criteria: ReviewCriteria
    dest_course: Course
    existing_keys: set[tuple[str, str]]
    dry_run: bool
    delete_from_source: bool
    to_delete: list[ReviewCriteria]


@dataclass(frozen=True)
class CriteriaCopyBatchData:
    source_criteria: list[ReviewCriteria]
    dest_course: Course
    existing_keys: set[tuple[str, str]]
    dry_run: bool
    delete_from_source: bool
    to_delete: list[ReviewCriteria]


@dataclass(frozen=True)
class MigrationSummaryData:
    created: list[ReviewCriteria]
    deleted: list[ReviewCriteria]
    dest_course: Course
    dry_run: bool
    delete_in_source: bool


def list_criteria(course: Course) -> list[ReviewCriteria]:
    """List all criteria for a course."""
    ordered_criteria = course.reviewcriteria_set.all().order_by("id")
    return list(ordered_criteria)


def criteria_key(criteria: ReviewCriteria) -> tuple[str, str]:
    return criteria.description, criteria.review_criteria_type


def existing_criteria_keys(
    criteria_list: list[ReviewCriteria],
) -> set[tuple[str, str]]:
    keys = set()
    for criteria in criteria_list:
        key = criteria_key(criteria)
        keys.add(key)
    return keys


def copied_criteria_for_dry_run(
    criteria: ReviewCriteria,
    delete_from_source: bool,
    to_delete: list[ReviewCriteria],
) -> ReviewCriteria:
    print(f"  + Would create: {criteria.description}")
    if delete_from_source:
        to_delete.append(criteria)
    return criteria


def create_copied_criteria(
    criteria: ReviewCriteria,
    dest_course: Course,
    delete_from_source: bool,
    to_delete: list[ReviewCriteria],
) -> ReviewCriteria:
    new_criteria = ReviewCriteria.objects.create(
        course=dest_course,
        description=criteria.description,
        options=criteria.options,
        review_criteria_type=criteria.review_criteria_type,
    )
    print(f"  ✓ Created: {new_criteria.description}")
    if delete_from_source:
        to_delete.append(criteria)
    return new_criteria


def copy_single_criteria(data: CriteriaCopyData) -> ReviewCriteria | None:
    if criteria_key(data.criteria) in data.existing_keys:
        print(f"  ⊘ Skipping existing: {data.criteria.description}")
        return None

    if data.dry_run:
        return copied_criteria_for_dry_run(
            data.criteria,
            data.delete_from_source,
            data.to_delete,
        )

    return create_copied_criteria(
        data.criteria,
        data.dest_course,
        data.delete_from_source,
        data.to_delete,
    )


def delete_source_criteria(
    criteria_list: list[ReviewCriteria],
    dry_run: bool,
) -> None:
    if dry_run or not criteria_list:
        return

    print()
    for criteria in criteria_list:
        print(f"  ✗ Deleting from source: {criteria.description}")
        criteria.delete()


def copy_source_criteria(data: CriteriaCopyBatchData) -> list[ReviewCriteria]:
    created = []
    for criteria in data.source_criteria:
        copy_data = CriteriaCopyData(
            criteria=criteria,
            dest_course=data.dest_course,
            existing_keys=data.existing_keys,
            dry_run=data.dry_run,
            delete_from_source=data.delete_from_source,
            to_delete=data.to_delete,
        )
        copied = copy_single_criteria(copy_data)
        if copied is not None:
            created.append(copied)
    return created


def build_criteria_copy_batch(
    source_course: Course,
    dest_course: Course,
    dry_run: bool,
    delete_from_source: bool,
) -> CriteriaCopyBatchData:
    source_criteria = list_criteria(source_course)
    dest_existing = list_criteria(dest_course)
    existing_keys = existing_criteria_keys(dest_existing)
    to_delete = []
    return CriteriaCopyBatchData(
        source_criteria=source_criteria,
        dest_course=dest_course,
        existing_keys=existing_keys,
        dry_run=dry_run,
        delete_from_source=delete_from_source,
        to_delete=to_delete,
    )


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
    batch_data = build_criteria_copy_batch(
        source_course=source_course,
        dest_course=dest_course,
        dry_run=dry_run,
        delete_from_source=delete_from_source,
    )
    created = copy_source_criteria(batch_data)

    if delete_from_source:
        delete_source_criteria(batch_data.to_delete, dry_run)

    return created, batch_data.to_delete


def parse_args():
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
    return parser.parse_args()


def get_course(slug: str, label: str) -> Course:
    try:
        return Course.objects.get(slug=slug)
    except Course.DoesNotExist:
        print(f"Error: {label} course '{slug}' not found")
        sys.exit(1)


def print_migration_header(
    source_course: Course,
    dest_course: Course,
    dry_run: bool,
) -> None:
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

    if dry_run:
        print("DRY RUN - No changes will be made")
        print()


def print_migration_summary(data: MigrationSummaryData) -> None:
    print("-" * 60)
    if data.dry_run:
        print(f"Would create {len(data.created)} criteria")
        if data.delete_in_source:
            print(f"Would delete {len(data.deleted)} criteria from source")
    else:
        print(f"Created {len(data.created)} criteria")
        if data.delete_in_source:
            print(f"Deleted {len(data.deleted)} criteria from source")

    if not data.dry_run:
        dest_criteria_after = list_criteria(data.dest_course)
        print(f"Destination course now has {len(dest_criteria_after)} criteria")


def main():
    args = parse_args()
    source_course = get_course(args.source_course, "Source")
    dest_course = get_course(args.dest_course, "Destination")

    print_migration_header(source_course, dest_course, args.dry_run)

    print("Migrating criteria:")
    print("-" * 60)

    created, deleted = copy_criteria(
        source_course,
        dest_course,
        dry_run=args.dry_run,
        delete_from_source=args.delete_in_source
    )

    summary_data = MigrationSummaryData(
        created=created,
        deleted=deleted,
        dest_course=dest_course,
        dry_run=args.dry_run,
        delete_in_source=args.delete_in_source,
    )
    print_migration_summary(summary_data)


if __name__ == "__main__":
    main()
