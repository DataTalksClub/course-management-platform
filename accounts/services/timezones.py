"""Timezone helpers for account preferences and backend date rendering."""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from django.utils import timezone

DEFAULT_TIMEZONE = "UTC"
DEFAULT_USER_DATETIME_FORMAT = "%-d %B %Y (%a), %H:%M"
EMAIL_DEADLINE_DATETIME_FORMAT = "%A, %-d %B %Y, %H:%M"


@dataclass(frozen=True)
class TimezoneOption:
    value: str
    label: str
    offset_minutes: int


def is_valid_timezone(timezone_name: str) -> bool:
    """Return whether ``timezone_name`` is a valid IANA timezone."""
    if not timezone_name:
        return False
    try:
        ZoneInfo(str(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def user_timezone_name(user, browser_timezone: str = "") -> str:
    """Return saved timezone, then browser-cookie timezone, then UTC."""
    timezone_name = getattr(user, "preferred_timezone", "") or ""
    if is_valid_timezone(timezone_name):
        return timezone_name
    if is_valid_timezone(browser_timezone):
        return browser_timezone
    return DEFAULT_TIMEZONE


def build_timezone_options() -> list[TimezoneOption]:
    """Return IANA timezones labeled with current GMT offset, west to east."""
    now_utc = timezone.now().astimezone(UTC)
    options = []
    for timezone_name in available_timezones():
        tz = ZoneInfo(timezone_name)
        offset = now_utc.astimezone(tz).utcoffset()
        if offset is None:
            continue
        offset_minutes = int(offset.total_seconds() // 60)
        options.append(
            TimezoneOption(
                value=timezone_name,
                label=f"{_format_offset(offset_minutes)} {timezone_name}",
                offset_minutes=offset_minutes,
            )
        )
    return sorted(options, key=lambda option: (option.offset_minutes, option.value))


def get_timezone_label(timezone_name: str) -> str:
    """Return the current offset label for a timezone, or an empty string."""
    if not is_valid_timezone(timezone_name):
        return ""
    now_utc = timezone.now().astimezone(UTC)
    offset = now_utc.astimezone(ZoneInfo(timezone_name)).utcoffset()
    if offset is None:
        return timezone_name
    return f"{_format_offset(int(offset.total_seconds() // 60))} {timezone_name}"


def format_user_datetime(
    value: datetime,
    viewer=None,
    *,
    fmt: str | None = None,
) -> str:
    """Format ``value`` in the saved timezone, browser cookie, or UTC."""
    if not isinstance(value, datetime):
        return ""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    user = getattr(viewer, "user", viewer)
    browser_timezone = ""
    cookies = getattr(viewer, "COOKIES", None)
    if cookies is not None:
        browser_timezone = unquote(cookies.get("browser_timezone", ""))

    timezone_name = user_timezone_name(user, browser_timezone)
    localized = value.astimezone(ZoneInfo(timezone_name))
    return localized.strftime(fmt or DEFAULT_USER_DATETIME_FORMAT)


def format_deadline_for_user(value: datetime, user=None) -> dict:
    """Render a deadline instant using the user's saved timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    timezone_name = user_timezone_name(user)
    local = value.astimezone(ZoneInfo(timezone_name))
    weekday = local.strftime("%A")
    date = local.strftime("%-d %B %Y")
    time = local.strftime("%H:%M")
    return {
        "deadline_iso": value.isoformat(),
        "deadline_weekday": weekday,
        "deadline_date": date,
        "deadline_time": time,
        "deadline_timezone": timezone_name,
        "deadline_summary": f"{weekday}, {date}, {time} {timezone_name}",
    }


def _format_offset(offset_minutes: int) -> str:
    sign = "+" if offset_minutes >= 0 else "-"
    absolute_minutes = abs(offset_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    return f"GMT{sign}{hours:02d}:{minutes:02d}"
