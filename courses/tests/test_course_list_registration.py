from django.utils import timezone

from courses.tests.course_list_base import CourseListViewTestBase


class CourseListRegistrationTest(CourseListViewTestBase):
    def test_course_list_shows_registration_before_course_start(self):
        self.course.start_date = timezone.localdate() + timezone.timedelta(
            days=7
        )
        self.course.end_date = timezone.localdate() + timezone.timedelta(
            days=77
        )
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.save()

        response = self.course_list_response()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )
