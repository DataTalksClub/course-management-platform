"""Bounded, set-based score writes without Django's per-cell CASE trees."""

from django.db import connection


def update_scoring_rows(model, rows, field_names):
    """Update already calculated numeric/boolean scores in the caller's transaction.

    Both supported databases (PostgreSQL and SQLite) support UPDATE FROM and
    VALUES CTEs. Identifiers come only from model metadata; values are bound.
    Bound each statement's parameters and Python memory independently of size.
    """
    fields = [model._meta.pk] + [model._meta.get_field(name) for name in field_names]
    quote = connection.ops.quote_name
    columns = [quote(field.column) for field in fields]
    table = quote(model._meta.db_table)
    row_size = len(fields)
    limit = connection.features.max_query_params or 10000
    batch_size = min(500, limit // row_size)
    assignments = ", ".join(f"{col} = scores.{col}" for col in columns[1:])
    with connection.cursor() as cursor:
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            params = [
                field.get_db_prep_save(getattr(row, field.attname), connection)
                for row in batch for field in fields
            ]
            placeholders = ", ".join(
                "(" + ", ".join(["%s"] * row_size) + ")" for _ in batch
            )
            cursor.execute(
                f"WITH scores ({', '.join(columns)}) AS (VALUES {placeholders}) "
                f"UPDATE {table} AS target SET {assignments} FROM scores "
                f"WHERE target.{columns[0]} = scores.{columns[0]}",
                params,
            )
