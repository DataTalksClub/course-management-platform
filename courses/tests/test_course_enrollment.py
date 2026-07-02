from django.urls import reverse

from courses.models import Enrollment
from courses.tests.course_view_base import (
    CourseDetailViewTestBase,
    credentials,
)


class CourseEnrollmentDisplayTest(CourseDetailViewTestBase):
    def test_not_enrolled_but_can_edit_details(self):
        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "enrollment", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        enrollment = form.instance
        self.assertEqual(enrollment.student.id, self.user.id)

    def test_course_view_does_not_auto_enroll(self):
        self.enrollment.delete()

        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        ).count()
        self.assertEqual(enrollment_count, 0)

        self.client.login(**credentials)
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        ).count()
        self.assertEqual(
            enrollment_count,
            0,
            "Course view should not auto-enroll users",
        )
