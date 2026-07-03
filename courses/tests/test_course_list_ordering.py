from datetime import timedelta

from django.utils import timezone

from courses.models import Course
from courses.tests.course_list_base import CourseListViewTestBase


class CourseListOrderingTest(CourseListViewTestBase):
    """Homepage courses split into active / open registration / archive."""

    def create_course(self, slug, **kwargs):
        return Course.objects.create(
            title=kwargs.pop("title", slug),
            slug=slug,
            visible=True,
            **kwargs,
        )

    def test_courses_split_into_three_tiers(self):
        today = timezone.localdate()

        started = self.create_course(
            "running-course",
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=30),
            registration_url="https://example.com/register",
        )
        upcoming = self.create_course(
            "upcoming-course",
            start_date=today + timedelta(days=14),
            end_date=today + timedelta(days=60),
            registration_url="https://example.com/register",
        )
        archived = self.create_course("archived-course", finished=True)

        response = self.course_list_response()
        active = {c.slug for c in response.context["active_courses"]}
        open_reg = {
            c.slug for c in response.context["open_registration_courses"]
        }
        finished = {c.slug for c in response.context["finished_courses"]}

        self.assertIn(started.slug, active)
        self.assertNotIn(started.slug, open_reg)

        self.assertIn(upcoming.slug, open_reg)
        self.assertNotIn(upcoming.slug, active)

        self.assertIn(archived.slug, finished)

    def test_future_course_without_registration_stays_active(self):
        today = timezone.localdate()
        future_no_reg = self.create_course(
            "future-no-registration",
            start_date=today + timedelta(days=14),
            end_date=today + timedelta(days=60),
        )

        response = self.course_list_response()
        active = {c.slug for c in response.context["active_courses"]}
        open_reg = {
            c.slug for c in response.context["open_registration_courses"]
        }

        self.assertIn(future_no_reg.slug, active)
        self.assertNotIn(future_no_reg.slug, open_reg)

    def test_open_registration_section_rendered(self):
        today = timezone.localdate()
        self.create_course(
            "upcoming-course",
            title="Upcoming Course",
            start_date=today + timedelta(days=14),
            registration_url="https://example.com/register",
        )

        response = self.course_list_response()
        content = response.content.decode()

        self.assertIn("Open registration", content)
        self.assertIn("Registration open", content)
