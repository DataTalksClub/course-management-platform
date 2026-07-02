from django.urls import reverse

from courses.tests.course_view_base import CourseDetailViewTestBase


class CourseDashboardLinkTest(CourseDetailViewTestBase):
    def test_course_detail_hides_dashboard_until_first_homework_scored(self):
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Course dashboard")
        dashboard_url = reverse(
            "dashboard",
            kwargs={"course_slug": self.course.slug},
        )
        self.assertNotContains(
            response,
            dashboard_url,
        )

    def test_course_detail_shows_dashboard_after_first_homework_scored(self):
        self.course.first_homework_scored = True
        self.course.save()
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course dashboard")
        dashboard_url = reverse(
            "dashboard",
            kwargs={"course_slug": self.course.slug},
        )
        self.assertContains(
            response,
            dashboard_url,
        )
