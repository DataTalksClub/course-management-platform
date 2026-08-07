from django.test import Client, TestCase

from accounts.models import CustomUser
from courses.models import Course, Enrollment

RELAY_DISABLED_SETTINGS = {
    "RELAY_URL": "",
    "RELAY_API_KEY": "",
    "RELAY_CLIENT": "",
    "RELAY_AUDIENCE": "",
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
