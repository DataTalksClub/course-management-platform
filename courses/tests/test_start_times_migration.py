from datetime import UTC, date, datetime
from importlib import import_module
from unittest.mock import Mock

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from courses.models import Course, Homework, Project


class StartTimeBackfillTests(TestCase):
    def test_only_known_course_boundaries_are_backfilled(self):
        course = Course.objects.create(
            title="Known",
            slug="known",
            description="",
            start_date=date(2026, 1, 5),
            end_date=date(2026, 2, 1),
        )
        unknown = Course.objects.create(
            title="Unknown", slug="unknown", description=""
        )
        invalid = Course.objects.create(
            title="Invalid",
            slug="invalid",
            description="",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )
        end = datetime(2026, 2, 1, tzinfo=UTC)
        homework = Homework.objects.create(
            course=course, slug="hw", title="HW", due_date=end
        )
        project = Project.objects.create(
            course=course,
            slug="project",
            title="Project",
            submission_due_date=end,
            peer_review_due_date=end,
        )
        migration = import_module("courses.migrations.0045_start_times")
        schema_editor = Mock(connection=connection)
        migration.backfill_course_starts(apps, schema_editor)
        for item in (course, unknown, invalid, homework, project):
            item.refresh_from_db()
        self.assertEqual(
            course.starts_at, datetime(2026, 1, 5, tzinfo=UTC)
        )
        for item in (unknown, invalid, homework, project):
            self.assertIsNone(item.starts_at)
        explicit = datetime(2026, 1, 5, 17, tzinfo=UTC)
        course.starts_at = explicit
        course.save()
        migration.backfill_course_starts(apps, schema_editor)
        course.refresh_from_db()
        self.assertEqual(course.starts_at, explicit)


class StartTimeSchemaMigrationTests(TransactionTestCase):
    def test_migration_preserves_deadlines_and_backfills_known_date(
        self,
    ):
        before = [("courses", "0044_alter_emailcampaign_status")]
        after = [("courses", "0045_start_times")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old_apps = executor.loader.project_state(before).apps
            old_course = old_apps.get_model("courses", "Course")
            old_homework = old_apps.get_model("courses", "Homework")
            course = old_course.objects.create(
                slug="legacy",
                title="Legacy",
                description="",
                start_date=date(2026, 1, 5),
            )
            due = datetime(2026, 1, 12, tzinfo=UTC)
            homework = old_homework.objects.create(
                course=course,
                slug="hw",
                title="HW",
                due_date=due,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new_apps = executor.loader.project_state(after).apps
            migrated = new_apps.get_model(
                "courses", "Course"
            ).objects.get(pk=course.pk)
            migrated_hw = new_apps.get_model(
                "courses", "Homework"
            ).objects.get(pk=homework.pk)
            self.assertEqual(
                migrated.starts_at, datetime(2026, 1, 5, tzinfo=UTC)
            )
            self.assertIsNone(migrated_hw.starts_at)
            self.assertEqual(migrated_hw.due_date, due)
        finally:
            MigrationExecutor(connection).migrate(after)
