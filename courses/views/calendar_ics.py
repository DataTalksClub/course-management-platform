from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone

from django.utils import timezone


@dataclass(frozen=True)
class CalendarEventData:
    uid: str
    summary: str
    start: object
    url: str
    description: str
    dtstamp: object


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_ics_datetime(value) -> str:
    if timezone.is_naive(value):
        current_timezone = timezone.get_current_timezone()
        value = timezone.make_aware(value, current_timezone)

    value = value.astimezone(datetime_timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def calendar_event(data: CalendarEventData) -> list[str]:
    end = data.start + timedelta(minutes=30)
    uid = escape_ics_text(data.uid)
    dtstamp = format_ics_datetime(data.dtstamp)
    start = format_ics_datetime(data.start)
    end_time = format_ics_datetime(end)
    summary = escape_ics_text(data.summary)
    description = escape_ics_text(data.description)
    url = escape_ics_text(data.url)

    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{start}",
        f"DTEND:{end_time}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"URL:{url}",
        "END:VEVENT",
    ]
