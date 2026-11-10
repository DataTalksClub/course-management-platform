from django.db import connection


def set_statement_timeout(timeout_ms):
    """Set the current PostgreSQL session's statement timeout in milliseconds."""
    if timeout_ms < 0:
        raise ValueError("timeout_ms cannot be negative")
    if connection.vendor != "postgresql":
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            [f"{timeout_ms}ms"],
        )
    return True
