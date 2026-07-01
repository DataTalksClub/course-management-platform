from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import TestCase

from accounts.services.timezones import (
    format_deadline_for_user,
    format_user_datetime,
)
from course_management.deadlines import ceil_to_next_hour

UTC = ZoneInfo("UTC")


class CeilToNextHourTest(TestCase):
    def test_rounds_up_sub_hour_components(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=15,
            minute=23,
            second=41,
            microsecond=500,
            tzinfo=UTC,
        )
        rounded_value = ceil_to_next_hour(value)
        expected_value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=16,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=UTC,
        )
        self.assertEqual(rounded_value, expected_value)

    def test_exact_hour_is_unchanged(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=15,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=UTC,
        )
        rounded_value = ceil_to_next_hour(value)
        self.assertEqual(rounded_value, value)

    def test_rolls_over_day_boundary(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=23,
            minute=30,
            second=0,
            microsecond=0,
            tzinfo=UTC,
        )
        rounded_value = ceil_to_next_hour(value)
        expected_value = datetime(
            year=2026,
            month=7,
            day=3,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=UTC,
        )
        self.assertEqual(rounded_value, expected_value)


class FormatDeadlineForUserTest(TestCase):
    def test_renders_utc_with_weekday(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=18,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        result = format_deadline_for_user(value)

        self.assertEqual(result["deadline_weekday"], "Thursday")
        self.assertEqual(result["deadline_date"], "2 July 2026")
        self.assertEqual(result["deadline_time"], "18:00")
        self.assertEqual(
            result["deadline_summary"], "Thursday, 2 July 2026, 18:00 UTC"
        )
        self.assertEqual(result["deadline_timezone"], "UTC")
        deadline_iso = value.isoformat()
        self.assertEqual(result["deadline_iso"], deadline_iso)

    def test_non_utc_instant_is_converted_to_utc(self):
        # 21:00 in Berlin (CEST, UTC+2) is 19:00 UTC.
        berlin_timezone = ZoneInfo("Europe/Berlin")
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=21,
            minute=0,
            second=0,
            tzinfo=berlin_timezone,
        )
        result = format_deadline_for_user(value)
        self.assertEqual(result["deadline_time"], "19:00")
        self.assertEqual(
            result["deadline_summary"],
            "Thursday, 2 July 2026, 19:00 UTC",
        )

    def test_renders_saved_user_timezone(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=22,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        user = SimpleNamespace(preferred_timezone="Europe/Berlin")

        result = format_deadline_for_user(value, user)

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
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=22,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        user = SimpleNamespace(preferred_timezone="")
        request = SimpleNamespace(
            user=user,
            COOKIES={"browser_timezone": "Europe%2FBerlin"},
        )

        result = format_user_datetime(value, request)

        self.assertEqual(result, "3 July 2026 (Fri), 00:00")

    def test_saved_timezone_overrides_browser_timezone_cookie(self):
        value = datetime(
            year=2026,
            month=7,
            day=2,
            hour=22,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        user = SimpleNamespace(preferred_timezone="America/New_York")
        request = SimpleNamespace(
            user=user,
            COOKIES={"browser_timezone": "Europe%2FBerlin"},
        )

        result = format_user_datetime(value, request)

        self.assertEqual(result, "2 July 2026 (Thu), 18:00")
