from courses.tests.course_view_base import CourseDetailViewTestBase


class CourseCertificateViewTests(CourseDetailViewTestBase):
    def test_course_view_with_certificate(self):
        certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.certificate_url = certificate_url
        self.enrollment.save()

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.context["certificate_url"], certificate_url)
        self.assertContains(response, "Download Certificate")
        self.assertContains(response, f'href="{certificate_url}"')

    def test_course_view_without_certificate(self):
        self.enrollment.certificate_url = None
        self.enrollment.save()

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")

    def test_course_view_certificate_not_shown_when_not_authenticated(self):
        self.enrollment.certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.save()

        response = self.get_course_response()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")
