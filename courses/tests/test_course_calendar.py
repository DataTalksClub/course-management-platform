from django.urls import reverse

from courses.tests.course_view_base import CourseDetailViewTestBase


class CourseCalendarLinkTest(CourseDetailViewTestBase):
    def test_course_detail_shows_calendar_feed_link(self):
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendar feed")
        self.assertNotContains(response, "primer-button\">Calendar feed")
        self.assertContains(
            response,
            "All deadlines are shown in your timezone.",
        )
        self.assertNotContains(response, "account timezone")
        account_settings_url = (
            f'{reverse("account_settings")}#display-preferences-section'
        )
        self.assertNotContains(
            response,
            account_settings_url,
        )
        calendar_url = reverse(
            "course_calendar",
            kwargs={"course_slug": self.course.slug},
        )
        self.assertContains(
            response,
            calendar_url,
        )


class CourseCalendarFeedTest(CourseDetailViewTestBase):
    def test_course_calendar_feed(self):
        url = reverse(
            "course_calendar",
            kwargs={"course_slug": self.course.slug},
        )

        response = self.client.get(url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "text/calendar; charset=utf-8",
        )
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("VERSION:2.0", content)
        self.assertIn("X-WR-CALNAME:Test Course deadlines", content)
        self.assertIn(
            "SUMMARY:Test Course: Submitted Homework deadline",
            content,
        )
        self.assertIn(
            "SUMMARY:Test Course: Open Project submission deadline",
            content,
        )
        self.assertIn(
            "SUMMARY:Test Course: Open Project peer review deadline",
            content,
        )
        event_count = content.count("BEGIN:VEVENT")
        self.assertEqual(event_count, 7)
