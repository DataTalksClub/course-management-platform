from django.urls import reverse

from courses.models import Course
from courses.tests.course_list_base import CourseListViewTestBase


class CourseListVisibilityTest(CourseListViewTestBase):
    def test_course_visibility_in_list(self):
        Course.objects.create(
            title="Visible Course",
            slug="visible-course",
            visible=True,
        )
        Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False,
        )

        response = self.course_list_response()

        self.assertEqual(response.status_code, 200)
        course_slugs = self.visible_course_slugs(response)
        self.assertIn("visible-course", course_slugs)
        self.assertNotIn("hidden-course", course_slugs)

    def test_hidden_course_accessible_via_direct_link(self):
        hidden_course = Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False,
        )

        url = reverse("course", kwargs={"course_slug": "hidden-course"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], hidden_course)
