#!/usr/bin/env python3
"""Load a converted RDS SQLite export into the local Django database.

The RDS export converter creates a SQLite file from Parquet data. That
file is useful as a row source, but it does not have Django's SQLite
schema details such as primary keys, constraints, and empty tables. This
script creates a fresh migrated Django SQLite database, copies rows from
the export into that schema, validates it, and swaps it into db/db.sqlite3.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path("/tmp/rds-export")
DEFAULT_PATTERN = "rds-prod-*.db"
DEFAULT_TARGET = PROJECT_ROOT / "db" / "db.sqlite3"
DEFAULT_WORK_DIR = PROJECT_ROOT / ".tmp"
DEFAULT_ADMIN_PASSWORD = "admin"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load a converted RDS SQLite export into the local Django "
            "SQLite database."
        )
    )
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
    return parser.parse_args()


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def latest_export(source_dir: Path, pattern: str) -> Path:
    candidates = [
        path
        for path in source_dir.glob(pattern)
        if path.is_file() and path.stat().st_size > 0
    ]
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

    return {
        model._meta.db_table: model
        for model in apps.get_models(include_auto_created=True)
    }


def django_field_default(model: Any, column: str) -> tuple[bool, Any]:
    from django.db.models import NOT_PROVIDED

    if model is None:
        return False, None

    for field in model._meta.fields:
        if field.column != column:
            continue

        if field.default is not NOT_PROVIDED:
            default = (
                field.default()
                if callable(field.default)
                else field.default
            )
            return True, default

        if field.null:
            return True, None

        return False, None

    return False, None


def table_names(cursor: sqlite3.Cursor) -> set[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def pragma_table_info(
    cursor: sqlite3.Cursor,
    table: str,
) -> list[sqlite3.Row]:
    cursor.execute(f'PRAGMA table_info("{table}")')
    return cursor.fetchall()


def copy_rows(source_db: Path, target_db: Path) -> None:
    model_by_table = setup_django()

    source = sqlite3.connect(source_db)
    target = sqlite3.connect(target_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row

    source_cursor = source.cursor()
    target_cursor = target.cursor()

    source_tables = sorted(table_names(source_cursor))
    target_tables = table_names(target_cursor)

    skip_tables = {"sqlite_sequence", "django_migrations"}
    imported: list[tuple[str, int, int]] = []
    skipped: list[tuple[str, str]] = []
    defaults_used: set[tuple[str, str, Any]] = set()

    target_cursor.execute("PRAGMA foreign_keys=OFF")

    for table in source_tables:
        if table in skip_tables:
            skipped.append((table, "managed by local migrations"))
            continue

        if table not in target_tables:
            skipped.append((table, "not in local Django schema"))
            continue

        source_info = pragma_table_info(source_cursor, table)
        target_info = pragma_table_info(target_cursor, table)
        source_columns = {row["name"] for row in source_info}
        insert_columns: list[str] = []
        default_values: dict[str, Any] = {}
        missing_required: list[str] = []
        model = model_by_table.get(table)

        for column_info in target_info:
            column = column_info["name"]
            not_null = bool(column_info["notnull"])
            db_default = column_info["dflt_value"]
            is_primary_key = bool(column_info["pk"])

            if column in source_columns:
                insert_columns.append(column)
                continue

            if is_primary_key:
                continue

            has_default, default = django_field_default(model, column)
            if has_default:
                insert_columns.append(column)
                default_values[column] = default
                defaults_used.add((table, column, default))
            elif not not_null or db_default is not None:
                continue
            else:
                missing_required.append(column)

        if missing_required:
            raise RuntimeError(
                f"{table}: source export is missing required local "
                f"columns without defaults: {missing_required}"
            )

        if not insert_columns:
            skipped.append((table, "no insertable columns"))
            continue

        quoted_columns = ", ".join(
            f'"{column}"' for column in insert_columns
        )
        placeholders = ", ".join("?" for _ in insert_columns)
        source_select_columns = [
            column
            for column in insert_columns
            if column in source_columns
        ]
        quoted_select_columns = ", ".join(
            f'"{column}"' for column in source_select_columns
        )

        target_cursor.execute(f'DELETE FROM "{table}"')
        source_cursor.execute(
            f'SELECT {quoted_select_columns} FROM "{table}"'
        )

        row_count = 0
        while True:
            batch = source_cursor.fetchmany(5000)
            if not batch:
                break

            values = [
                tuple(
                    source_row[column]
                    if column in source_columns
                    else default_values[column]
                    for column in insert_columns
                )
                for source_row in batch
            ]
            target_cursor.executemany(
                f'INSERT INTO "{table}" ({quoted_columns}) '
                f"VALUES ({placeholders})",
                values,
            )
            row_count += len(values)

        imported.append((table, row_count, len(insert_columns)))

    target.commit()
    refresh_sqlite_sequences(target_cursor, imported)
    target.commit()

    target_cursor.execute("PRAGMA foreign_keys=ON")
    violations = target_cursor.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
    if violations:
        details = "\n".join(str(tuple(row)) for row in violations[:20])
        raise RuntimeError(
            "Foreign-key check failed with "
            f"{len(violations)} violations:\n"
            f"{details}"
        )

    print(f"Imported {len(imported)} tables from {source_db}:")
    for table, rows, columns in imported:
        print(f"  {table}: {rows} rows, {columns} columns")

    if defaults_used:
        print("Filled local-only columns with Django defaults:")
        for table, column, default in sorted(defaults_used):
            print(f"  {table}.{column} = {default!r}")

    if skipped:
        print("Skipped tables:")
        for table, reason in skipped:
            print(f"  {table}: {reason}")

    source.close()
    target.close()


def refresh_sqlite_sequences(
    cursor: sqlite3.Cursor, imported: list[tuple[str, int, int]]
) -> None:
    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='sqlite_sequence'"
    )
    if cursor.fetchone() is None:
        return

    for table, _rows, _columns in imported:
        table_info = pragma_table_info(cursor, table)
        primary_keys = [
            row["name"] for row in table_info if row["pk"] == 1
        ]
        if primary_keys != ["id"]:
            continue

        cursor.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
        max_id = cursor.fetchone()[0]
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


def main() -> int:
    args = parse_args()
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

    print(f"Source export: {source_db}")
    print(f"Rebuilt DB:    {rebuilt_db}")
    print(f"Target DB:     {target_db}")

    migrate_empty_db(rebuilt_db)
    copy_rows(source_db, rebuilt_db)
    create_admin_user(rebuilt_db, args)
    validate_rebuilt_db(rebuilt_db)

    if args.no_replace:
        print(
            "Built and validated DB without replacing target: "
            f"{rebuilt_db}"
        )
        return 0

    backup_db = replace_target(rebuilt_db, target_db, work_dir)
    if backup_db:
        print(f"Backed up previous DB to: {backup_db}")
    print(f"Loaded rebuilt export into: {target_db}")

    if args.keep_rebuilt:
        print(f"Kept rebuilt DB at: {rebuilt_db}")
    else:
        rebuilt_db.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
