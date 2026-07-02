"""Deadline computation and formatting for notifications.

`ceil_to_next_hour` is used to derive auto-set deadlines (e.g. peer review
opens for 7 days, rounded up to a whole hour).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
