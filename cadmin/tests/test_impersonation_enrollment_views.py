from django.urls import reverse

from courses.models import Enrollment

from .impersonation_base import (
    ImpersonationCadminViewTestBase,
    admin_credentials,
)


class ImpersonationEnrollmentCadminViewTests(
    ImpersonationCadminViewTestBase,
):
    def test_enrollment_edit_has_login_as_button(self):
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        url = reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )
        login_url = self.login_as_user_url()
        course_url = reverse(
            "course",
            kwargs={"course_slug": self.course.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in as student")
        self.assertContains(response, login_url)
        self.assertContains(response, f'value="{course_url}"')
