"""Apply database migrations under a PostgreSQL advisory lock."""

import os

from django.core.management import BaseCommand, call_command
from django.core.management.base import CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Apply migrations under the CMP release advisory lock."

    LOCK_KEY = 0x434D5001
    DEFAULT_STATEMENT_TIMEOUT_MS = 300_000

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        database_alias = options["database"]
        connection = connections[database_alias]
        if connection.vendor != "postgresql":
            raise CommandError("migrate_with_lock requires PostgreSQL")

        try:
            statement_timeout_ms = int(
                os.environ.get(
                    "CMP_MIGRATION_STATEMENT_TIMEOUT_MS",
                    str(self.DEFAULT_STATEMENT_TIMEOUT_MS),
                )
            )
        except ValueError as exc:
            raise CommandError(
                "CMP_MIGRATION_STATEMENT_TIMEOUT_MS must be a positive integer"
            ) from exc
        if statement_timeout_ms <= 0:
            raise CommandError(
                "CMP_MIGRATION_STATEMENT_TIMEOUT_MS must be a positive integer"
            )

        connection.ensure_connection()
        acquired = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('lock_timeout', %s, false)", ["5s"]
                )
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, false)",
                    [f"{statement_timeout_ms}ms"],
                )
                cursor.execute(
                    "SELECT pg_advisory_lock(%s)", [self.LOCK_KEY]
                )
                acquired = True

            self.stdout.write("Applying database migrations under CMP lock")
            call_command(
                "migrate",
                database=database_alias,
                interactive=False,
                verbosity=options.get("verbosity", 1),
            )
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s)", [self.LOCK_KEY]
                    )
