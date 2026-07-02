import json

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, Enrollment


class EnrollmentExportsAPITestBase(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create(
            username="staff",
            email="staff@example.com",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def certificates_url(self):
        return f"/api/courses/{self.course.slug}/certificates"

    def post_certificates(self, payload):
        url = self.certificates_url()
        request_body = json.dumps(payload)
        return self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

    def create_student(self, email):
        return CustomUser.objects.create(username=email, email=email)

    def create_enrollment(self, email, certificate_url=""):
        student = self.create_student(email)
        return Enrollment.objects.create(
            student=student,
            course=self.course,
            certificate_url=certificate_url,
        )

    def certificate_item(self, email, path):
        return {
            "email": email,
            "certificate_path": path,
        }

    def assert_certificate_url(self, enrollment, expected_url):
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.certificate_url, expected_url)
