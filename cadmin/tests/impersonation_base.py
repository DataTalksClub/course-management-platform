from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course, User


credentials = {
    "username": "test@test.com",
    "email": "test@test.com",
    "password": "12345",
}

admin_credentials = {
    "username": "admin@test.com",
    "password": "admin123",
}


class ImpersonationCadminViewTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def login_as_user_url(self, user=None):
        target_user = user
        if target_user is None:
            target_user = self.user
        return reverse(
            "loginas-user-login",
            kwargs={"user_id": target_user.id},
        )
