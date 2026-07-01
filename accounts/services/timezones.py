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
        normalized_timezone_name = str(timezone_name)
        ZoneInfo(normalized_timezone_name)
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
    timezone_names = available_timezones()
    for timezone_name in timezone_names:
        tz = ZoneInfo(timezone_name)
        offset = now_utc.astimezone(tz).utcoffset()
        if offset is None:
            continue
        offset_minutes = int(offset.total_seconds() // 60)
        offset_label = _format_offset(offset_minutes)
        option = TimezoneOption(
            value=timezone_name,
            label=f"{offset_label} {timezone_name}",
            offset_minutes=offset_minutes,
        )
        options.append(option)
    return sorted(options, key=timezone_option_sort_key)


def timezone_option_sort_key(option: TimezoneOption):
    return option.offset_minutes, option.value


def get_timezone_label(timezone_name: str) -> str:
    """Return the current offset label for a timezone, or an empty string."""
    if not is_valid_timezone(timezone_name):
        return ""
    now_utc = timezone.now().astimezone(UTC)
    timezone_info = ZoneInfo(timezone_name)
    localized_now = now_utc.astimezone(timezone_info)
    offset = localized_now.utcoffset()
    if offset is None:
        return timezone_name
    offset_minutes = int(offset.total_seconds() // 60)
    offset_label = _format_offset(offset_minutes)
    return f"{offset_label} {timezone_name}"


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
        browser_timezone_cookie = cookies.get("browser_timezone", "")
        browser_timezone = unquote(browser_timezone_cookie)

    timezone_name = user_timezone_name(user, browser_timezone)
    timezone_info = ZoneInfo(timezone_name)
    localized = value.astimezone(timezone_info)
    if fmt:
        date_format = fmt
    else:
        date_format = DEFAULT_USER_DATETIME_FORMAT
    formatted_value = localized.strftime(date_format)
    return formatted_value


def format_deadline_for_user(value: datetime, user=None) -> dict:
    """Render a deadline instant using the user's saved timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    timezone_name = user_timezone_name(user)
    timezone_info = ZoneInfo(timezone_name)
    local = value.astimezone(timezone_info)
    deadline_weekday = local.strftime("%A")
    deadline_date = local.strftime("%-d %B %Y")
    deadline_time = local.strftime("%H:%M")
    deadline_iso = value.isoformat()
    return {
        "deadline_iso": deadline_iso,
        "deadline_weekday": deadline_weekday,
        "deadline_date": deadline_date,
        "deadline_time": deadline_time,
        "deadline_timezone": timezone_name,
        "deadline_summary": (
            f"{deadline_weekday}, {deadline_date}, "
            f"{deadline_time} {timezone_name}"
        ),
    }


def _format_offset(offset_minutes: int) -> str:
    if offset_minutes >= 0:
        sign = "+"
    else:
        sign = "-"
    absolute_minutes = abs(offset_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    return f"GMT{sign}{hours:02d}:{minutes:02d}"
