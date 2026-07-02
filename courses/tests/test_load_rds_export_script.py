import sqlite3
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from django.test import SimpleTestCase

from courses.models import Course
from scripts.load_rds_export import (
    ColumnDefault,
    ColumnCopyData,
    CopySummary,
    ImportedTable,
    TableCopyPlan,
    django_field_default,
    missing_required_columns,
    print_copy_summary,
    refresh_sqlite_sequences,
)


def column_info(name, *, notnull=False, default=None, pk=False):
    notnull_value = int(notnull)
    pk_value = int(pk)
    return {
        "name": name,
        "notnull": notnull_value,
        "dflt_value": default,
        "pk": pk_value,
    }


class LoadRdsExportScriptTest(SimpleTestCase):
    def copy_plan_without_insert_columns(self):
        return TableCopyPlan(
            table="courses_course",
            insert_columns=[],
            source_columns={"slug", "title"},
            default_values={},
        )

    def target_course_column_info(self):
        return [
            column_info("id", pk=True),
            column_info("slug", notnull=True),
            column_info("title", notnull=True),
            column_info("visible", notnull=True),
            column_info("nullable_local"),
            column_info("db_default_local", notnull=True, default="'x'"),
            column_info("required_local", notnull=True),
        ]

    def course_column_copy_data(self, plan, defaults_used):
        return ColumnCopyData(
            model=Course,
            table="courses_course",
            source_columns={"slug", "title"},
            plan=plan,
            defaults_used=defaults_used,
        )

    def assert_missing_required_copy_plan(self, missing, plan, defaults_used):
        expected_default = ColumnDefault(
            "courses_course",
            "visible",
            True,
        )

        self.assertEqual(missing, ["required_local"])
        self.assertEqual(plan.insert_columns, ["slug", "title", "visible"])
        self.assertEqual(plan.default_values, {"visible": True})
        self.assertEqual(defaults_used, {expected_default})

    def test_missing_required_columns_builds_copy_plan(self):
        plan = self.copy_plan_without_insert_columns()
        target_info = self.target_course_column_info()
        defaults_used = set()
        column_data = self.course_column_copy_data(plan, defaults_used)

        missing = missing_required_columns(target_info, column_data)

        self.assert_missing_required_copy_plan(
            missing,
            plan,
            defaults_used,
        )

    def test_django_field_default_uses_model_defaults_and_nullable_fields(self):
        visible_default = django_field_default(Course, "visible")
        self.assertEqual(visible_default, (True, True))
        start_date_default = django_field_default(Course, "start_date")
        self.assertEqual(
            start_date_default,
            (True, None),
        )
        missing_default = django_field_default(Course, "missing")
        self.assertEqual(missing_default, (False, None))
        missing_model_default = django_field_default(None, "visible")
        self.assertEqual(missing_model_default, (False, None))

    def test_refresh_sqlite_sequences_updates_id_primary_key_tables(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            "CREATE TABLE imported (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
        )
        cursor.execute("CREATE TABLE keyed (slug TEXT PRIMARY KEY)")
        cursor.executemany(
            "INSERT INTO imported(id, name) VALUES (?, ?)",
            [(3, "three"), (7, "seven")],
        )
        cursor.execute(
            "UPDATE sqlite_sequence SET seq=1 WHERE name='imported'"
        )

        refresh_sqlite_sequences(
            cursor,
            [
                ImportedTable("imported", 2, 2),
                ImportedTable("keyed", 0, 1),
            ],
        )

        sequence = cursor.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='imported'"
        ).fetchone()[0]
        self.assertEqual(sequence, 7)

    def test_print_copy_summary_outputs_each_section(self):
        imported_table = ImportedTable("courses_course", 2, 3)
        default_info = ColumnDefault("courses_course", "visible", True)
        summary = CopySummary(
            imported=[imported_table],
            skipped=[("django_migrations", "managed locally")],
            defaults_used={default_info},
        )

        out = StringIO()
        source_path = Path("source.db")
        with redirect_stdout(out):
            print_copy_summary(source_path, summary)

        output = out.getvalue()
        self.assertIn("Imported 1 tables from source.db", output)
        self.assertIn("courses_course: 2 rows, 3 columns", output)
        self.assertIn("courses_course.visible = True", output)
        self.assertIn("django_migrations: managed locally", output)
