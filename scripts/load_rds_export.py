#!/usr/bin/env python3
"""Load a converted RDS SQLite export into the local Django database.

The RDS export converter creates a SQLite file from Parquet data. That
file is useful as a row source, but it does not have Django's SQLite
schema details such as primary keys, constraints, and empty tables. This
script creates a fresh migrated Django SQLite database, copies rows from
the export into that schema, validates it, and swaps it into db/db.sqlite3.
"""

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path("/tmp/rds-export")
DEFAULT_PATTERN = "rds-prod-*.db"
DEFAULT_TARGET = PROJECT_ROOT / "db" / "db.sqlite3"
DEFAULT_WORK_DIR = PROJECT_ROOT / ".tmp"
DEFAULT_ADMIN_PASSWORD = "admin"
SKIP_TABLES = {"sqlite_sequence", "django_migrations"}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class TableCopyPlan:
    table: str
    insert_columns: list[str]
    source_columns: set[str]
    default_values: dict[str, Any]


@dataclass(frozen=True)
class ImportedTable:
    table: str
    rows: int
    columns: int


@dataclass(frozen=True)
class ColumnDefault:
    table: str
    column: str
    default: Any


@dataclass
class CopySummary:
    imported: list[ImportedTable] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    defaults_used: set[ColumnDefault] = field(default_factory=set)


@dataclass(frozen=True)
class ColumnCopyData:
    model: Any
    table: str
    source_columns: set[str]
    plan: TableCopyPlan
    defaults_used: set[ColumnDefault]


@dataclass(frozen=True)
class TableCopyBuildData:
    table: str
    source_cursor: sqlite3.Cursor
    target_cursor: sqlite3.Cursor
    model_by_table: dict[str, Any]
    defaults_used: set[ColumnDefault]


@dataclass(frozen=True)
class SourceTableCopyData:
    table: str
    source_cursor: sqlite3.Cursor
    target_cursor: sqlite3.Cursor
    target_tables: set[str]
    model_by_table: dict[str, Any]
    summary: CopySummary


@dataclass
class ImportPaths:
    source_db: Path
    rebuilt_db: Path
    target_db: Path
    work_dir: Path


def add_source_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-db",
        type=Path,
        help="Specific converted RDS SQLite export to load.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory to search when --source-db is omitted. "
        f"Default: {DEFAULT_SOURCE_DIR}",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help=(
            "Glob for converted CMP exports. "
            f"Default: {DEFAULT_PATTERN}"
        ),
    )


def add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target-db",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"Local SQLite DB to replace. Default: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help=(
            "Directory for temporary DBs/backups. "
            f"Default: {DEFAULT_WORK_DIR}"
        ),
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help=(
            "Build and validate the DB, but leave --target-db unchanged."
        ),
    )
    parser.add_argument(
        "--keep-rebuilt",
        action="store_true",
        help="Keep the rebuilt DB in .tmp after replacing the target.",
    )


def add_admin_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--admin-email",
        default=os.getenv("CMP_ADMIN_EMAIL", "alexey@datatalks.club"),
        help=(
            "Admin email to create/reset after import. "
            "Can also be set with CMP_ADMIN_EMAIL."
        ),
    )
    parser.add_argument(
        "--admin-password",
        default=os.getenv("CMP_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
        help=(
            "Admin password. Defaults to the same password used by "
            f"make data: {DEFAULT_ADMIN_PASSWORD!r}. Can also be set "
            "with CMP_ADMIN_PASSWORD."
        ),
    )
    parser.add_argument(
        "--admin-user-id",
        type=int,
        default=None,
        help=(
            "Target a specific imported user id when the admin email has "
            "duplicates."
        ),
    )
    parser.add_argument(
        "--no-admin",
        action="store_true",
        help="Do not create/reset an admin user after import.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load a converted RDS SQLite export into the local Django "
            "SQLite database."
        )
    )
    add_source_options(parser)
    add_target_options(parser)
    add_admin_options(parser)
    return parser


def parse_args() -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args()


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def latest_export(source_dir: Path, pattern: str) -> Path:
    candidates = []
    matching_paths = source_dir.glob(pattern)
    for path in matching_paths:
        if path.is_file() and path.stat().st_size > 0:
            candidates.append(path)
    if not candidates:
        raise SystemExit(
            f"No export DBs found in {source_dir} matching {pattern!r}."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_manage_py(args: list[str], db_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = sqlite_url(db_path)
    command = [sys.executable, "manage.py", *args]
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def migrate_empty_db(db_path: Path) -> None:
    db_path.unlink(missing_ok=True)
    run_manage_py(["migrate", "--noinput"], db_path)


def setup_django() -> dict[str, Any]:
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "course_management.settings",
    )

    import django
    from django.apps import apps

    django.setup()

    model_by_table = {}
    models = apps.get_models(include_auto_created=True)
    for model in models:
        table = model._meta.db_table
        model_by_table[table] = model
    return model_by_table


def django_field_default(model: Any, column: str) -> tuple[bool, Any]:
    from django.db.models import NOT_PROVIDED

    model_field = django_field_for_column(model, column)
    if model_field is None:
        return False, None
    if model_field.default is not NOT_PROVIDED:
        if callable(model_field.default):
            default = model_field.default()
        else:
            default = model_field.default
        return True, default
    if model_field.null:
        return True, None
    return False, None


def django_field_for_column(model: Any, column: str):
    if model is None:
        return None
    model_fields = model._meta.fields
    for model_field in model_fields:
        if model_field.column == column:
            return model_field
    return None


def table_names(cursor: sqlite3.Cursor) -> set[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    names = set()
    rows = cursor.fetchall()
    for row in rows:
        name = row[0]
        names.add(name)
    return names


def pragma_table_info(
    cursor: sqlite3.Cursor,
    table: str,
) -> list[sqlite3.Row]:
    cursor.execute(f'PRAGMA table_info("{table}")')
    return cursor.fetchall()


def connect_databases(
    source_db: Path,
    target_db: Path,
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(target_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    return source, target


def missing_required_columns(
    target_info: list[sqlite3.Row],
    column_data: ColumnCopyData,
) -> list[str]:
    missing_required: list[str] = []

    for column_info in target_info:
        missing_column = apply_column_copy_plan(
            column_info,
            column_data,
        )
        if missing_column:
            missing_required.append(missing_column)

    return missing_required


def apply_column_copy_plan(
    column_info: sqlite3.Row,
    data: ColumnCopyData,
) -> str:
    column = column_info["name"]
    if column in data.source_columns:
        data.plan.insert_columns.append(column)
        return ""
    if bool(column_info["pk"]):
        return ""

    has_default, default = django_field_default(data.model, column)
    if has_default:
        data.plan.insert_columns.append(column)
        data.plan.default_values[column] = default
        default_info = ColumnDefault(data.table, column, default)
        data.defaults_used.add(default_info)
        return ""
    if column_allows_local_value(column_info):
        return ""
    return column


def column_allows_local_value(column_info: sqlite3.Row) -> bool:
    return not bool(column_info["notnull"]) or column_info["dflt_value"] is not None


def build_table_copy_plan(data: TableCopyBuildData) -> TableCopyPlan:
    source_info = pragma_table_info(data.source_cursor, data.table)
    target_info = pragma_table_info(data.target_cursor, data.table)
    source_columns = set()
    for row in source_info:
        column = row["name"]
        source_columns.add(column)
    plan = TableCopyPlan(
        table=data.table,
        insert_columns=[],
        source_columns=source_columns,
        default_values={},
    )
    column_data = ColumnCopyData(
        model=data.model_by_table.get(data.table),
        table=data.table,
        source_columns=source_columns,
        plan=plan,
        defaults_used=data.defaults_used,
    )
    missing_required = missing_required_columns(
        target_info,
        column_data,
    )

    if missing_required:
        raise RuntimeError(
            f"{data.table}: source export is missing required local "
            f"columns without defaults: {missing_required}"
        )

    return plan


def quoted_csv(columns: list[str]) -> str:
    quoted_columns = []
    for column in columns:
        quoted_column = f'"{column}"'
        quoted_columns.append(quoted_column)
    return ", ".join(quoted_columns)


def table_source_columns(plan: TableCopyPlan) -> list[str]:
    columns = []
    insert_columns = plan.insert_columns
    for column in insert_columns:
        if column in plan.source_columns:
            columns.append(column)
    return columns


def row_values(
    source_row: sqlite3.Row,
    plan: TableCopyPlan,
) -> tuple[Any, ...]:
    values = []
    insert_columns = plan.insert_columns
    for column in insert_columns:
        if column in plan.source_columns:
            value = source_row[column]
        else:
            value = plan.default_values[column]
        values.append(value)
    return tuple(values)


def insert_batch_sql(plan: TableCopyPlan) -> str:
    placeholders = []
    insert_columns = plan.insert_columns
    for _column in insert_columns:
        placeholders.append("?")
    placeholder_sql = ", ".join(placeholders)
    return (
        f'INSERT INTO "{plan.table}" ({quoted_csv(plan.insert_columns)}) '
        f"VALUES ({placeholder_sql})"
    )


def copy_table_rows(
    source_cursor: sqlite3.Cursor,
    target_cursor: sqlite3.Cursor,
    plan: TableCopyPlan,
) -> int:
    source_select_columns = table_source_columns(plan)
    target_cursor.execute(f'DELETE FROM "{plan.table}"')
    source_cursor.execute(
        f'SELECT {quoted_csv(source_select_columns)} FROM "{plan.table}"'
    )

    row_count = 0
    while True:
        batch = source_cursor.fetchmany(5000)
        if not batch:
            break

        values = []
        for source_row in batch:
            value = row_values(source_row, plan)
            values.append(value)
        target_cursor.executemany(insert_batch_sql(plan), values)
        row_count += len(values)

    return row_count


def validate_foreign_keys(target_cursor: sqlite3.Cursor) -> None:
    target_cursor.execute("PRAGMA foreign_keys=ON")
    violations = target_cursor.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
    if violations:
        detail_lines = []
        violation_sample = violations[:20]
        for row in violation_sample:
            detail = str(tuple(row))
            detail_lines.append(detail)
        details = "\n".join(detail_lines)
        raise RuntimeError(
            "Foreign-key check failed with "
            f"{len(violations)} violations:\n"
            f"{details}"
        )


def print_copy_summary(source_db: Path, summary: CopySummary) -> None:
    print_imported_tables(source_db, summary.imported)
    print_defaults_used(summary.defaults_used)
    print_skipped_tables(summary.skipped)


def print_imported_tables(
    source_db: Path,
    imported: list[ImportedTable],
) -> None:
    print(f"Imported {len(imported)} tables from {source_db}:")
    for imported_table in imported:
        print(
            f"  {imported_table.table}: "
            f"{imported_table.rows} rows, "
            f"{imported_table.columns} columns"
        )


def print_defaults_used(defaults_used: set[ColumnDefault]) -> None:
    if defaults_used:
        print("Filled local-only columns with Django defaults:")
        sorted_defaults = sorted(
            defaults_used,
            key=lambda item: (
                item.table,
                item.column,
                repr(item.default),
            ),
        )
        for default_info in sorted_defaults:
            print(
                f"  {default_info.table}.{default_info.column} "
                f"= {default_info.default!r}"
            )


def print_skipped_tables(skipped: list[tuple[str, str]]) -> None:
    if skipped:
        print("Skipped tables:")
        for table, reason in skipped:
            print(f"  {table}: {reason}")


def source_table_skip_reason(data: SourceTableCopyData) -> str | None:
    if data.table in SKIP_TABLES:
        return "managed by local migrations"

    if data.table not in data.target_tables:
        return "not in local Django schema"

    return None


def skip_source_table(data: SourceTableCopyData, reason: str) -> None:
    skipped_table = (data.table, reason)
    data.summary.skipped.append(skipped_table)


def execute_table_copy_plan(
    data: SourceTableCopyData,
    plan: TableCopyPlan,
) -> None:
    row_count = copy_table_rows(
        data.source_cursor,
        data.target_cursor,
        plan,
    )
    imported_table = ImportedTable(
        data.table,
        row_count,
        len(plan.insert_columns),
    )
    data.summary.imported.append(imported_table)


def copy_source_table(data: SourceTableCopyData) -> None:
    skip_reason = source_table_skip_reason(data)
    if skip_reason is not None:
        skip_source_table(data, skip_reason)
        return

    build_data = TableCopyBuildData(
        table=data.table,
        source_cursor=data.source_cursor,
        target_cursor=data.target_cursor,
        model_by_table=data.model_by_table,
        defaults_used=data.summary.defaults_used,
    )
    plan = build_table_copy_plan(build_data)

    if not plan.insert_columns:
        skip_source_table(data, "no insertable columns")
        return

    execute_table_copy_plan(data, plan)


def copy_rows(source_db: Path, target_db: Path) -> None:
    model_by_table = setup_django()
    source, target = connect_databases(source_db, target_db)

    try:
        source_cursor = source.cursor()
        target_cursor = target.cursor()
        source_tables = sorted(table_names(source_cursor))
        target_tables = table_names(target_cursor)
        summary = CopySummary()

        target_cursor.execute("PRAGMA foreign_keys=OFF")
        for table in source_tables:
            table_data = SourceTableCopyData(
                table=table,
                source_cursor=source_cursor,
                target_cursor=target_cursor,
                target_tables=target_tables,
                model_by_table=model_by_table,
                summary=summary,
            )
            copy_source_table(table_data)

        target.commit()
        refresh_sqlite_sequences(target_cursor, summary.imported)
        target.commit()
        validate_foreign_keys(target_cursor)
        print_copy_summary(source_db, summary)
    finally:
        source.close()
        target.close()


def refresh_sqlite_sequences(
    cursor: sqlite3.Cursor, imported: list[ImportedTable]
) -> None:
    if not sqlite_sequence_exists(cursor):
        return

    for imported_table in imported:
        table = imported_table.table
        if table_has_single_id_primary_key(cursor, table):
            upsert_sqlite_sequence(
                cursor,
                table,
                table_max_id(cursor, table),
            )


def sqlite_sequence_exists(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='sqlite_sequence'"
    )
    return cursor.fetchone() is not None


def table_has_single_id_primary_key(cursor: sqlite3.Cursor, table: str) -> bool:
    table_info = pragma_table_info(cursor, table)
    primary_keys = []
    for row in table_info:
        if row["pk"] == 1:
            primary_keys.append(row["name"])
    return primary_keys == ["id"]


def table_max_id(cursor: sqlite3.Cursor, table: str) -> int:
    cursor.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
    return cursor.fetchone()[0]


def upsert_sqlite_sequence(cursor: sqlite3.Cursor, table: str, max_id: int) -> None:
    cursor.execute(
        "UPDATE sqlite_sequence SET seq=? WHERE name=?",
        (max_id, table),
    )
    if cursor.rowcount == 0:
        cursor.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
            (table, max_id),
        )


def validate_rebuilt_db(db_path: Path) -> None:
    run_manage_py(["migrate", "--check"], db_path)
    run_manage_py(["check"], db_path)


def create_admin_user(db_path: Path, args: argparse.Namespace) -> None:
    if args.no_admin:
        print("Skipping admin user creation.")
        return

    env = os.environ.copy()
    env["DATABASE_URL"] = sqlite_url(db_path)

    command = [
        sys.executable,
        "scripts/create_superuser.py",
        "--email",
        args.admin_email,
    ]
    if args.admin_password:
        command.extend(["--password", args.admin_password])
    if args.admin_user_id is not None:
        command.extend(["--user-id", str(args.admin_user_id)])

    print(f"Creating/resetting admin user: {args.admin_email}")
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def replace_target(
    rebuilt_db: Path,
    target_db: Path,
    work_dir: Path,
) -> Path | None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if not target_db.exists():
        shutil.copy2(rebuilt_db, target_db)
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_db = work_dir / f"{target_db.name}.before-rds-{timestamp}"
    shutil.copy2(target_db, backup_db)
    shutil.copy2(rebuilt_db, target_db)
    return backup_db


def resolve_import_paths(args: argparse.Namespace) -> ImportPaths:
    source_db = (
        args.source_db.resolve()
        if args.source_db
        else latest_export(args.source_dir, args.pattern).resolve()
    )
    target_db = args.target_db.resolve()
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rebuilt_db = work_dir / f"rds-import-{timestamp}.db"

    return ImportPaths(
        source_db=source_db,
        rebuilt_db=rebuilt_db,
        target_db=target_db,
        work_dir=work_dir,
    )


def print_import_paths(paths: ImportPaths) -> None:
    print(f"Source export: {paths.source_db}")
    print(f"Rebuilt DB:    {paths.rebuilt_db}")
    print(f"Target DB:     {paths.target_db}")


def rebuild_database(paths: ImportPaths, args: argparse.Namespace) -> None:
    migrate_empty_db(paths.rebuilt_db)
    copy_rows(paths.source_db, paths.rebuilt_db)
    create_admin_user(paths.rebuilt_db, args)
    validate_rebuilt_db(paths.rebuilt_db)


def replace_rebuilt_database(paths: ImportPaths, args: argparse.Namespace) -> None:
    backup_db = replace_target(paths.rebuilt_db, paths.target_db, paths.work_dir)
    if backup_db:
        print(f"Backed up previous DB to: {backup_db}")
    print(f"Loaded rebuilt export into: {paths.target_db}")

    if args.keep_rebuilt:
        print(f"Kept rebuilt DB at: {paths.rebuilt_db}")
    else:
        paths.rebuilt_db.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    paths = resolve_import_paths(args)
    print_import_paths(paths)
    rebuild_database(paths, args)

    if args.no_replace:
        print(
            "Built and validated DB without replacing target: "
            f"{paths.rebuilt_db}"
        )
        return 0

    replace_rebuilt_database(paths, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
