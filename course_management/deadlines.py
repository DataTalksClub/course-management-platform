"""Deadline computation and formatting for notifications.

`ceil_to_next_hour` is used to derive auto-set deadlines (e.g. peer review
opens for 7 days, rounded up to a whole hour). `format_deadline_for_email`
renders a single deadline instant in the recipient's saved timezone, falling
back to UTC.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from accounts.services.timezones import format_deadline_for_user

UTC = ZoneInfo("UTC")


def ceil_to_next_hour(value: datetime) -> datetime:
    """Round a datetime up to the start of the next whole hour.

    A value already exactly on the hour is returned unchanged
    (15:00:00 -> 15:00:00); anything with sub-hour components is rounded up
    (15:23:41 -> 16:00:00).
    """
    if value.minute == 0 and value.second == 0 and value.microsecond == 0:
        return value
    truncated = value.replace(minute=0, second=0, microsecond=0)
    return truncated + timedelta(hours=1)


def format_deadline_for_email(value: datetime, user=None) -> dict:
    """Render a deadline instant for an email.

    Returns the weekday, date and time as separate pieces plus a ready-to-use
    ``deadline_summary`` line, e.g. "Thursday, 2 July 2026, 20:00 Europe/Berlin".
    """
    return format_deadline_for_user(value, user)
