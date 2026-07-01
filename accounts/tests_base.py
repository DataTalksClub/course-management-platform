from django.test import Client, TestCase

from accounts.models import CustomUser
from courses.models import Course, Enrollment

DATAMAILER_DISABLED_SETTINGS = {
    "DATAMAILER_URL": "",
    "DATAMAILER_API_KEY": "",
    "DATAMAILER_CLIENT": "",
    "DATAMAILER_AUDIENCE": "",
}


class AccountCourseTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="testpass123",
        )
        self.course = Course.objects.create(
            slug="data-course",
            title="Data Course",
            description="Learn data",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Student One",
        )
