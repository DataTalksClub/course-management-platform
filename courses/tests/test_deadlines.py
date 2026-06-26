from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import TestCase

from course_management.deadlines import (
    ceil_to_next_hour,
    format_deadline_for_email,
)
from accounts.services.timezones import format_user_datetime

UTC = ZoneInfo("UTC")


class CeilToNextHourTest(TestCase):
    def test_rounds_up_sub_hour_components(self):
        value = datetime(2026, 7, 2, 15, 23, 41, 500, tzinfo=UTC)
        self.assertEqual(
            ceil_to_next_hour(value),
            datetime(2026, 7, 2, 16, 0, 0, 0, tzinfo=UTC),
        )

    def test_exact_hour_is_unchanged(self):
        value = datetime(2026, 7, 2, 15, 0, 0, 0, tzinfo=UTC)
        self.assertEqual(ceil_to_next_hour(value), value)

    def test_rolls_over_day_boundary(self):
        value = datetime(2026, 7, 2, 23, 30, 0, 0, tzinfo=UTC)
        self.assertEqual(
            ceil_to_next_hour(value),
            datetime(2026, 7, 3, 0, 0, 0, 0, tzinfo=UTC),
        )


class FormatDeadlineForEmailTest(TestCase):
    def test_renders_utc_with_weekday(self):
        value = datetime(2026, 7, 2, 18, 0, 0, tzinfo=UTC)
        result = format_deadline_for_email(value)

        self.assertEqual(result["deadline_weekday"], "Thursday")
        self.assertEqual(result["deadline_date"], "2 July 2026")
        self.assertEqual(result["deadline_time"], "18:00")
        self.assertEqual(
            result["deadline_summary"], "Thursday, 2 July 2026, 18:00 UTC"
        )
        self.assertEqual(result["deadline_timezone"], "UTC")
        self.assertEqual(result["deadline_iso"], value.isoformat())

    def test_non_utc_instant_is_converted_to_utc(self):
        # 21:00 in Berlin (CEST, UTC+2) is 19:00 UTC.
        value = datetime(2026, 7, 2, 21, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        result = format_deadline_for_email(value)
        self.assertEqual(result["deadline_time"], "19:00")
        self.assertEqual(result["deadline_summary"], "Thursday, 2 July 2026, 19:00 UTC")

    def test_renders_saved_user_timezone(self):
        value = datetime(2026, 7, 2, 22, 0, 0, tzinfo=UTC)
        user = SimpleNamespace(preferred_timezone="Europe/Berlin")

        result = format_deadline_for_email(value, user)

        self.assertEqual(result["deadline_weekday"], "Friday")
        self.assertEqual(result["deadline_date"], "3 July 2026")
        self.assertEqual(result["deadline_time"], "00:00")
        self.assertEqual(result["deadline_timezone"], "Europe/Berlin")
        self.assertEqual(
            result["deadline_summary"],
            "Friday, 3 July 2026, 00:00 Europe/Berlin",
        )


class FormatUserDatetimeTest(TestCase):
    def test_uses_browser_timezone_cookie_when_profile_timezone_empty(self):
        value = datetime(2026, 7, 2, 22, 0, 0, tzinfo=UTC)
        request = SimpleNamespace(
            user=SimpleNamespace(preferred_timezone=""),
            COOKIES={"browser_timezone": "Europe%2FBerlin"},
        )

        result = format_user_datetime(value, request)

        self.assertEqual(result, "3 July 2026, 00:00 Europe/Berlin")

    def test_saved_timezone_overrides_browser_timezone_cookie(self):
        value = datetime(2026, 7, 2, 22, 0, 0, tzinfo=UTC)
        request = SimpleNamespace(
            user=SimpleNamespace(preferred_timezone="America/New_York"),
            COOKIES={"browser_timezone": "Europe%2FBerlin"},
        )

        result = format_user_datetime(value, request)

        self.assertEqual(result, "2 July 2026, 18:00 America/New_York")
