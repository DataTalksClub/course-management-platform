from django.test import SimpleTestCase

from courses.models import Course
from scripts.load_rds_export import (
    TableCopyPlan,
    missing_required_columns,
)


def column_info(name, *, notnull=False, default=None, pk=False):
    return {
        "name": name,
        "notnull": int(notnull),
        "dflt_value": default,
        "pk": int(pk),
    }


class LoadRdsExportScriptTest(SimpleTestCase):
    def test_missing_required_columns_builds_copy_plan(self):
        plan = TableCopyPlan(
            table="courses_course",
            insert_columns=[],
            source_columns={"slug", "title"},
            default_values={},
        )
        defaults_used = set()
        target_info = [
            column_info("id", pk=True),
            column_info("slug", notnull=True),
            column_info("title", notnull=True),
            column_info("visible", notnull=True),
            column_info("nullable_local"),
            column_info("db_default_local", notnull=True, default="'x'"),
            column_info("required_local", notnull=True),
        ]

        missing = missing_required_columns(
            Course,
            "courses_course",
            target_info,
            {"slug", "title"},
            plan,
            defaults_used,
        )

        self.assertEqual(missing, ["required_local"])
        self.assertEqual(plan.insert_columns, ["slug", "title", "visible"])
        self.assertEqual(plan.default_values, {"visible": True})
        self.assertEqual(defaults_used, {("courses_course", "visible", True)})
